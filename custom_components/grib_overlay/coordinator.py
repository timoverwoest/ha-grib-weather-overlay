"""Keeps cached GRIB overlay frames up to date for one config entry.

On each poll: ask the source for the latest run's filename. If it changed
since last time, download the run (a single archive containing one GRIB file
per lead time for KNMI), extract only the lead times inside the configured
forecast horizon, decode+render the enabled parameters for each of those,
cache the resulting PNGs on disk, and drop everything else (the archive
itself, members outside the horizon, and older runs beyond the retention
count) to keep bandwidth/disk bounded -- a HARMONIE run archive is roughly
850MB for ~49 lead times, far more than a home server should keep around.

None of that lives in /config: Home Assistant tars the config folder for every
backup, and this file churn both bloated and broke those backups. See
storage_paths for where the working files go instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tarfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import field_grid, grib_decode, render, storage_paths, velocity
from .const import (
    CONF_API_KEY,
    CONF_COLOR_SCALES,
    CONF_DATASET,
    CONF_FORECAST_HORIZON_HOURS,
    CONF_NOTIFICATION_API_KEY,
    CONF_PARAMETERS,
    CONF_RETAIN_RUNS,
    CONF_SOURCE,
    CONF_STORAGE_PATH,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_FORECAST_HORIZON_HOURS,
    DEFAULT_RETAIN_RUNS,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)
from .sources.base import (
    GribDatasetInfo,
    GribParameter,
    GribSource,
    GribSourceAuthError,
    GribSourceError,
)
from .sources.registry import get_source_class

_LOGGER = logging.getLogger(__name__)


def enabled_parameter_keys(entry: ConfigEntry) -> list[str]:
    """The parameters this entry renders: the options' choice, else the setup's."""
    if CONF_PARAMETERS in entry.options:
        return list(entry.options[CONF_PARAMETERS])
    return list(entry.data.get(CONF_PARAMETERS, []))


@dataclass
class Frame:
    parameter_key: str
    valid_time: datetime
    run_time: datetime
    png_path: Path
    bounds: tuple[float, float, float, float]
    legend: render.Legend
    # For vector (wind) parameters: leaflet-velocity JSON with the raw u/v grid.
    wind_path: Path | None = None
    # Compact scalar grid for click-value / meteogram point sampling.
    field_path: Path | None = None


class GribOverlayCoordinator(DataUpdateCoordinator[dict]):
    """One coordinator per config entry; owns one source + one dataset."""

    # Shared across all entries, toggled by the backup platform (backup.py).
    # Since 0.26 no working file lives under /config (see storage_paths), so a
    # backup can no longer trip over our churn. This pause is kept as a second
    # line of defence -- for the one-time /config cleanup on upgrade, and for
    # anyone who points storage_path back inside the config folder. While a
    # backup runs we skip processing a new run (and thus any deletion); the next
    # poll after the backup picks the run up.
    _backup_active: bool = False
    _backup_since: float = 0.0
    # Safety net: if async_post_backup never fires (e.g. a crashed/aborted
    # backup) resume normal operation after this long rather than pausing
    # downloads forever.
    _BACKUP_MAX_SECONDS = 1800
    # Guards the one-time removal of the 0.26-0.34 cache root (see
    # _remove_legacy_share_root), which runs in executor threads.
    _share_root_lock = threading.Lock()

    @classmethod
    def set_backup_active(cls, active: bool) -> None:
        cls._backup_active = active
        cls._backup_since = time.monotonic() if active else 0.0

    @classmethod
    def backup_in_progress(cls) -> bool:
        if not cls._backup_active:
            return False
        if time.monotonic() - cls._backup_since > cls._BACKUP_MAX_SECONDS:
            cls._backup_active = False
            return False
        return True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        update_minutes = entry.options.get(
            CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=update_minutes),
        )
        self.entry = entry
        source_cls = get_source_class(entry.data[CONF_SOURCE])
        session = async_get_clientsession(hass)
        # A separate notification/MQTT key (options override entry data) is used
        # for push updates when the user supplied one; sources that don't use it
        # ignore the kwarg.
        notification_key = entry.options.get(
            CONF_NOTIFICATION_API_KEY
        ) or entry.data.get(CONF_NOTIFICATION_API_KEY)
        self.source: GribSource = source_cls(
            session,
            entry.data[CONF_API_KEY],
            notification_api_key=notification_key,
            instance_id=entry.entry_id,  # stable MQTT client id across reloads
        )
        # Everything this integration writes lives outside every folder a backup
        # can include: our file churn used to abort backups outright
        # (FileNotFoundError on a member deleted mid-tar) and the cache made them
        # gigabytes heavier, while all of it can be downloaded again. See
        # storage_paths.
        configured = entry.options.get(CONF_STORAGE_PATH) or entry.data.get(CONF_STORAGE_PATH)
        self.storage_dir = storage_paths.entry_dir(configured, entry.entry_id)
        self._scratch_root = storage_paths.scratch_dir(configured, entry.entry_id)
        # Earlier locations -- /config (up to 0.25) and /share (0.26-0.34), both in
        # backups. Cleared once (see _migrate_legacy_storage) so an upgrade
        # actually shrinks the backup; never the folder in use now.
        self._legacy_storage_dirs = [
            legacy
            for legacy in (
                Path(hass.config.path(DOMAIN, entry.entry_id)),
                storage_paths.LEGACY_SHARE_ROOT / entry.entry_id,
            )
            if not storage_paths.overlaps(legacy, self.storage_dir)
        ]
        self._legacy_migrated = False
        # Optional per-parameter custom colour scales (baked into the PNG at
        # render time). Parsed once; the coordinator is recreated on an options
        # change, and a change invalidates cached runs so they re-render.
        self._color_scales = render.parse_color_scales(
            entry.options.get(CONF_COLOR_SCALES, "")
        )
        # Serialises run processing so the backup platform can wait for an
        # in-flight run to finish its file churn before the archive is walked.
        self._process_lock = asyncio.Lock()
        self._current_run_filename: str | None = None
        # A rejected key fails every poll, so the warning is logged once and
        # re-armed after the next success rather than repeated every interval.
        self._auth_warned = False
        # frames[parameter_key] = list[Frame] sorted by valid_time
        self.frames: dict[str, list[Frame]] = {}

    @property
    def _raw_dir(self) -> Path:
        """Scratch space for in-flight downloads (run archive, raw members)."""
        return self._scratch_root

    def _migrate_legacy_storage(self, in_use: list[Path]) -> None:
        """Blocking: get the caches of earlier versions out of the backup folders, once.

        Each is moved to the current root when that is a plain rename, and
        otherwise dropped -- it is a cache, and on Home Assistant OS /config,
        /share and /var/tmp are separate mounts anyway. ``in_use`` are the
        folders any entry is configured to use now; those are never touched.
        """
        if self._legacy_migrated:
            return
        for legacy in self._legacy_storage_dirs:
            if not legacy.is_dir() or any(storage_paths.overlaps(legacy, p) for p in in_use):
                continue
            moved = False
            try:
                if not self.storage_dir.exists():
                    self.storage_dir.parent.mkdir(parents=True, exist_ok=True)
                    legacy.rename(self.storage_dir)
                    moved = True
            except OSError as err:
                _LOGGER.debug("Could not move %s to %s: %s", legacy, self.storage_dir, err)
            if not moved:
                shutil.rmtree(legacy, ignore_errors=True)
            _LOGGER.warning(
                "%s the old GRIB cache at %s (now %s): it was part of Home "
                "Assistant backups, making them larger and able to fail on a file "
                "that vanished mid-backup",
                "Moved" if moved else "Removed",
                legacy,
                self.storage_dir,
            )
            # Drops /config/grib_overlay once the last entry has left it.
            try:
                legacy.parent.rmdir()
            except OSError:
                pass
        self._remove_legacy_share_root(in_use)
        self._legacy_migrated = True

    @classmethod
    def _remove_legacy_share_root(cls, in_use: list[Path]) -> None:
        """Blocking: drop what else 0.26-0.34 left in /share/grib_overlay.

        Its scratch and weather-chart folders, and the caches of entries that
        have since been deleted -- unless some entry is configured to use it.
        Every entry sets up at the same time, in executor threads: the lock
        makes one of them do it (and log it), not all.
        """
        root = storage_paths.LEGACY_SHARE_ROOT
        with cls._share_root_lock:
            if not root.is_dir() or any(storage_paths.overlaps(root, p) for p in in_use):
                return
            shutil.rmtree(root, ignore_errors=True)
            _LOGGER.warning("Removed the old GRIB cache folder %s (part of backups)", root)

    async def _async_migrate_legacy_storage(self) -> None:
        """Run the one-time cleanup of old cache folders, unless a backup is walking them."""
        if self._legacy_migrated or self.backup_in_progress():
            return
        in_use = [
            storage_paths.storage_root(
                e.options.get(CONF_STORAGE_PATH) or e.data.get(CONF_STORAGE_PATH)
            )
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.options.get(CONF_STORAGE_PATH) or e.data.get(CONF_STORAGE_PATH)
        ]
        await self.hass.async_add_executor_job(self._migrate_legacy_storage, in_use)

    def _auth_failure(self, err: GribSourceAuthError) -> str:
        """Log an actionable warning for a rejected key; return the failure text.

        DataUpdateCoordinator turns an UpdateFailed into a terse "Error fetching
        ... data" line that says nothing about which of the three keys is wrong,
        or that the entry will simply never update until it is fixed. Since a
        bad key is silent otherwise -- the card just stops getting new runs --
        say so explicitly, once.
        """
        if not self._auth_warned:
            self._auth_warned = True
            if err.status == 403:
                advice = (
                    "the key is recognised but is NOT authorised for dataset '%s'. "
                    "Request access to that dataset, or use a key that has it."
                    % self.entry.data[CONF_DATASET]
                )
            elif err.status == 401:
                advice = (
                    "the key is not recognised at all -- check for a typo or a "
                    "truncated paste, and note that a key can expire or be revoked."
                )
            else:
                advice = "check the key."
            _LOGGER.warning(
                "%s (%s): the API key was rejected (%s), so this source will not "
                "update until it is fixed -- %s Set it under Settings > Devices & "
                "services > GRIB Weather Overlay > Configure. Note that KNMI uses "
                "THREE separate keys: Open Data (this one), Notification Service "
                "(push/MQTT) and one for the observations dataset (station "
                "downloads); they are not interchangeable.",
                self.entry.title,
                self.source.name,
                err,
                advice,
            )
        return str(err)

    async def _async_drop_stale_scratch(self) -> None:
        """Remove leftovers from a run that was interrupted mid-flight.

        _process_new_run cleans its scratch dir in a finally, but a shutdown
        cancels that await too -- a restart in the middle of a download (or a
        crash, or a power cut) therefore strands up to a full run archive on
        disk. Nothing is in flight for this entry at setup, so the whole scratch
        tree can go.
        """
        await self.hass.async_add_executor_job(
            shutil.rmtree, self._raw_dir, True
        )

    async def async_setup(self) -> None:
        """Fast setup (does not download): restore cached frames, start push, poll timer.

        The heavy download/decode is deliberately NOT done here -- __init__.py
        kicks off the first refresh as a background task so entry setup returns
        immediately. On a restart the cached frames from a previous run are
        loaded from disk so the card has data straight away.
        """
        await self._async_migrate_legacy_storage()
        await self._async_drop_stale_scratch()
        run_filename, frames = await self.hass.async_add_executor_job(self._load_cached_frames)
        if run_filename:
            self._current_run_filename = run_filename
            self.frames = frames
            _LOGGER.debug(
                "Restored cached frames for run %s (%d parameters) from disk",
                run_filename,
                len(frames),
            )

        await self._async_start_notifications()

        # This coordinator has no entities/listeners, so it never self-schedules
        # periodic refreshes -- drive polling ourselves as a fallback for when
        # push notifications are unavailable.
        self._unsub_poll = async_track_time_interval(
            self.hass, self._scheduled_poll, self.update_interval
        )
        self.entry.async_on_unload(self._unsub_poll)

    @callback
    def _scheduled_poll(self, _now) -> None:
        self._start_refresh("poll")

    @callback
    def _start_refresh(self, reason: str) -> None:
        """Kick off a refresh as a config-entry BACKGROUND task.

        Not hass.async_create_task: a plain task is only cancelled in Home
        Assistant's "final writes" shutdown stage, and since decoding a run takes
        minutes, a restart mid-run reliably left a CancelledError traceback in
        the log. A background task is tied to the config entry, so it is
        cancelled quietly when the entry unloads (which shutdown does first).
        """
        self.entry.async_create_background_task(
            self.hass,
            self.async_request_refresh(),
            f"{DOMAIN}-{reason}-{self.entry.entry_id}",
        )

    async def _async_start_notifications(self) -> None:
        """Start push notifications if the source supports it.

        Best-effort: async_start_notifications never raises (the source
        catches its own connection errors), so a broken/unsupported push
        channel just leaves polling as the only update path.
        """
        if not self.source.supports_push_notifications:
            return
        try:
            datasets = await self.source.async_list_datasets()
        except GribSourceError:
            return  # the first poll will surface and retry the real error
        dataset = next((d for d in datasets if d.key == self.entry.data[CONF_DATASET]), None)
        if dataset is None:
            return
        await self.source.async_start_notifications(dataset, self._on_new_file_notified)

    def _on_new_file_notified(self, filename: str) -> None:
        """Push-notification callback, invoked on the event loop thread.

        Doesn't process the file directly: triggers a normal refresh, which
        re-lists files and reuses the exact same "already processed?" /
        download/extract/decode path polling uses. Keeps there being exactly
        one code path for handling a new run, whether discovered by push or
        by poll.
        """
        if filename == self._current_run_filename:
            return
        _LOGGER.debug("KNMI push notification for new run: %s", filename)
        self._start_refresh("push")

    async def _async_update_data(self) -> dict:
        try:
            datasets = await self.source.async_list_datasets()
        except GribSourceAuthError as err:
            raise UpdateFailed(self._auth_failure(err)) from err
        except GribSourceError as err:
            raise UpdateFailed(str(err)) from err

        dataset = next((d for d in datasets if d.key == self.entry.data[CONF_DATASET]), None)
        if dataset is None:
            raise UpdateFailed(f"Dataset '{self.entry.data[CONF_DATASET]}' not offered by source")

        try:
            files = await self.source.async_list_files(dataset, max_keys=1)
        except GribSourceAuthError as err:
            raise UpdateFailed(self._auth_failure(err)) from err
        except GribSourceError as err:
            raise UpdateFailed(str(err)) from err
        # Got a listing, so the key works; re-arm the warning for a later failure
        # (a revoked or rotated key should be reported again).
        if self._auth_warned:
            _LOGGER.warning("%s: the API key is accepted again.", self.entry.title)
            self._auth_warned = False
        if not files:
            raise UpdateFailed("Source returned no files for this dataset")

        latest = files[0]
        if self.hass.is_stopping:
            # A run takes minutes; starting one now just gets cancelled halfway
            # and leaves a scratch dir behind for the next start to clean up.
            return {"run_filename": self._current_run_filename, "dataset": dataset.key}
        if latest.filename != self._current_run_filename and not self.backup_in_progress():
            async with self._process_lock:
                # A backup may have started while we waited for the lock; the
                # download/decode below deletes files under /config, so bail and
                # let the next poll after the backup handle this run.
                if not self.backup_in_progress():
                    _LOGGER.debug(
                        "New run detected for %s: %s", dataset.key, latest.filename
                    )
                    await self._async_migrate_legacy_storage()
                    try:
                        await self._process_new_run(dataset, latest.filename)
                    except GribSourceError as err:
                        raise UpdateFailed(str(err)) from err
                    self._current_run_filename = latest.filename
                    await self.hass.async_add_executor_job(self._cleanup_old_runs)
        elif latest.filename != self._current_run_filename:
            _LOGGER.debug(
                "Backup in progress; deferring new run %s until it finishes",
                latest.filename,
            )

        return {"run_filename": self._current_run_filename, "dataset": dataset.key}

    async def _process_new_run(self, dataset: GribDatasetInfo, filename: str) -> None:
        enabled_keys = set(enabled_parameter_keys(self.entry))
        parameters = [p for p in dataset.parameters if p.key in enabled_keys]
        if not parameters:
            _LOGGER.warning("No parameters enabled for %s, skipping run %s", dataset.key, filename)
            return

        horizon_hours = self.entry.options.get(
            CONF_FORECAST_HORIZON_HOURS, DEFAULT_FORECAST_HORIZON_HOURS
        )
        run_dir = self.storage_dir / Path(filename).stem
        # Every raw byte -- the run archive and the GRIB members extracted from
        # it -- is created and deleted inside this scratch dir, kept apart from
        # the run directories (and well away from /config) so no backup can ever
        # trip over a file we are in the middle of removing.
        raw_dir = self._raw_dir / Path(filename).stem

        if getattr(self.source, "provides_archive", True):
            # KNMI: one .tar archive (~850 MB) holds every lead-time member.
            tar_path = raw_dir / filename
            await self.source.async_download_file(dataset, filename, tar_path)
            try:
                member_paths = await self.hass.async_add_executor_job(
                    self._extract_archive, tar_path, raw_dir
                )
            finally:
                await self.hass.async_add_executor_job(tar_path.unlink, True)
        else:
            # DWD/BSH: individual per-parameter/per-lead-time GRIB files.
            try:
                member_paths = await self.source.async_download_run(
                    dataset, filename, raw_dir, [p.key for p in parameters], horizon_hours
                )
            except BaseException:
                # e.g. a run that turned out to be still publishing: drop what
                # did arrive, the next poll starts over.
                await self.hass.async_add_executor_job(shutil.rmtree, raw_dir, True)
                raise

        try:
            new_frames = await self.hass.async_add_executor_job(
                self._decode_members, member_paths, run_dir, filename, parameters, horizon_hours
            )
            if any(new_frames.values()):
                self.frames = new_frames
            else:
                # A run that decoded to nothing (e.g. a provider briefly missing
                # its near-term files) must not blank a working source: keep the
                # previous run's frames and drop the empty run dir so it can't
                # shadow the good run on restore (_load_cached_frames requires
                # non-empty frames) or get retained in its place.
                _LOGGER.warning(
                    "Run %s for %s produced no frames; keeping the previous run",
                    filename,
                    dataset.key,
                )
                await self.hass.async_add_executor_job(shutil.rmtree, run_dir, True)
        finally:
            # Always drop the scratch copy, including when decoding blew up: it
            # now sits on real disk (not a tmpfs that a reboot clears), so a
            # leaked run archive would cost ~850MB until the next restart.
            # ignore_errors: a member may already be gone.
            await self.hass.async_add_executor_job(shutil.rmtree, raw_dir, True)

    def _extract_archive(self, tar_path: Path, raw_dir: Path) -> list[Path]:
        """Blocking: extract every regular member of a run archive into raw_dir."""
        raw_dir.mkdir(parents=True, exist_ok=True)
        member_paths: list[Path] = []
        with tarfile.open(tar_path, "r") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                extracted_path = raw_dir / Path(member.name).name
                with tar.extractfile(member) as src, extracted_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                member_paths.append(extracted_path)
        return member_paths

    def _decode_members(
        self,
        member_paths: list[Path],
        run_dir: Path,
        run_filename: str,
        parameters: list[GribParameter],
        horizon_hours: float,
    ) -> dict[str, list[Frame]]:
        """Blocking: filter each member by horizon, decode+render every parameter it holds.

        Works for both KNMI (each member is one lead time containing all
        parameters) and DWD (each file is one parameter for one lead time);
        parameters not present in a member just raise GribDecodeError and skip.
        """
        run_dir.mkdir(parents=True, exist_ok=True)
        new_frames: dict[str, list[Frame]] = {p.key: [] for p in parameters}
        run_time: datetime | None = None
        # Last seen run-total per accumulated parameter (see _deaccumulate).
        running_totals: dict[str, tuple[datetime, np.ndarray]] = {}

        for member_path in member_paths:
            try:
                valid_time, member_run_time = grib_decode.peek_valid_time(member_path)
            except (grib_decode.GribDecodeError, OSError) as err:
                # OSError covers a member that vanished/was unreadable -- skip it
                # rather than aborting the whole run (the next poll re-fetches).
                _LOGGER.debug("Skipping unreadable member %s: %s", member_path.name, err)
                member_path.unlink(missing_ok=True)
                continue

            run_time = run_time or member_run_time
            if valid_time - member_run_time > timedelta(hours=horizon_hours):
                member_path.unlink(missing_ok=True)
                continue

            for parameter in parameters:
                try:
                    frame = self._process_parameter(
                        parameter, member_path, run_dir, running_totals
                    )
                except (grib_decode.GribDecodeError, OSError) as err:
                    _LOGGER.debug(
                        "Parameter %s not in member %s: %s", parameter.key, member_path.name, err
                    )
                    continue
                new_frames[parameter.key].append(frame)
            member_path.unlink(missing_ok=True)

        for frames in new_frames.values():
            frames.sort(key=lambda f: f.valid_time)
        self._write_frames_manifest(run_dir, run_filename, new_frames, horizon_hours)
        return new_frames

    @staticmethod
    def _deaccumulate(
        field: grib_decode.DecodedField,
        running_totals: dict[str, tuple[datetime, np.ndarray]],
    ) -> grib_decode.DecodedField:
        """Turn a total-since-run-start into the amount since the previous lead time.

        Needs the parameter's lead times in ascending order (the source's
        promise, see GribParameter.accumulated). The first lead time is only
        usable when it is the run start or one hour after it; a later first
        total spans several hours and would read as one very wet hour.
        """
        key = field.parameter_key
        total = field.data
        previous = running_totals.get(key)
        running_totals[key] = (field.valid_time, total)
        if previous is not None and previous[1].shape == total.shape:
            amount = total - previous[1]
        elif field.valid_time - field.run_time <= timedelta(hours=1):
            amount = total
        else:
            raise grib_decode.GribDecodeError(
                f"{key}: no earlier total to subtract for {field.valid_time:%Y-%m-%d %H:%M}"
            )
        # Packing rounding can leave a hair below zero where nothing fell.
        field.data = np.maximum(amount, 0.0)
        return field

    def _process_parameter(
        self,
        parameter: GribParameter,
        grib_path: Path,
        run_dir: Path,
        running_totals: dict[str, tuple[datetime, np.ndarray]] | None = None,
    ) -> Frame:
        """Decode one parameter, render the PNG, and (for wind) save velocity JSON."""
        wind_path: Path | None = None
        if parameter.kind == "vector":
            vec = grib_decode.decode_vector_components(grib_path, parameter)
            magnitude = np.hypot(vec.u, vec.v) * parameter.scale + parameter.offset
            field = grib_decode.DecodedField(
                parameter_key=parameter.key,
                data=magnitude,
                lats=vec.lats,
                lons=vec.lons,
                valid_time=vec.valid_time,
                run_time=vec.run_time,
                unit=parameter.unit,
            )
            wind_path = run_dir / f"{parameter.key}_{vec.valid_time:%Y%m%dT%H%M}.wind.json"
            wind_path.write_text(
                json.dumps(
                    velocity.build_velocity_data(vec.u, vec.v, vec.lats, vec.lons, vec.valid_time)
                )
            )
        else:
            field = grib_decode.decode_parameter(grib_path, parameter)
            if parameter.accumulated:
                field = self._deaccumulate(
                    field, running_totals if running_totals is not None else {}
                )

        frame_obj, legend = render.render_field(
            field,
            colormap=parameter.colormap,
            value_range=parameter.value_range,
            custom_colormap=self._color_scales.get(parameter.key),
        )
        stem = f"{parameter.key}_{field.valid_time:%Y%m%dT%H%M}"
        png_path = run_dir / f"{stem}.png"
        png_path.write_bytes(frame_obj.png_bytes)

        # Store a compact scalar grid (in display units) for point sampling.
        field_path = run_dir / f"{stem}.field.json"
        field_path.write_text(
            json.dumps(field_grid.build_field(field.data, field.lats, field.lons))
        )

        return Frame(
            parameter_key=parameter.key,
            valid_time=field.valid_time,
            run_time=field.run_time,
            png_path=png_path,
            bounds=frame_obj.bounds,
            legend=legend,
            wind_path=wind_path,
            field_path=field_path,
        )

    # -- disk cache (skip re-downloading an already-processed run on restart) ---

    MANIFEST_NAME = "frames.json"
    # Bump when the on-disk artifacts a run produces change (e.g. field grids
    # added in v0.5.0) or need regenerating (v3: PNGs re-rendered with the
    # Web-Mercator row warp so wide overlays line up). A cached run with an
    # older version is re-processed so the corrected artifacts get generated.
    MANIFEST_VERSION = 3

    def _color_scales_signature(self) -> str:
        """Stable fingerprint of the active custom colour scales. A cached run
        rendered with a different fingerprint is re-processed so the PNGs match.
        Empty when no custom scales are set, so upgrades don't force a re-render."""
        return json.dumps(self._color_scales, sort_keys=True) if self._color_scales else ""

    def _write_frames_manifest(
        self,
        run_dir: Path,
        run_filename: str,
        frames: dict[str, list[Frame]],
        horizon_hours: float | None = None,
    ) -> None:
        """Persist frame metadata so a restart can rebuild self.frames from disk."""
        manifest = {
            "manifest_version": self.MANIFEST_VERSION,
            "color_scales": self._color_scales_signature(),
            "run_filename": run_filename,
            "horizon_hours": horizon_hours,
            "frames": {
                key: [
                    {
                        "valid_time": f.valid_time.isoformat(),
                        "run_time": f.run_time.isoformat(),
                        "png": f.png_path.name,
                        "wind": f.wind_path.name if f.wind_path else None,
                        "field": f.field_path.name if f.field_path else None,
                        "bounds": list(f.bounds),
                        "legend": {
                            "unit": f.legend.unit,
                            "min_value": f.legend.min_value,
                            "max_value": f.legend.max_value,
                            "stops": [dict(s) for s in f.legend.stops],
                        },
                    }
                    for f in flist
                ]
                for key, flist in frames.items()
            },
        }
        (run_dir / self.MANIFEST_NAME).write_text(json.dumps(manifest))

    def _load_cached_frames(self) -> tuple[str | None, dict[str, list[Frame]]]:
        """Blocking: rebuild frames for the newest run that has a valid manifest + PNGs."""
        if not self.storage_dir.exists():
            return None, {}
        enabled = set(enabled_parameter_keys(self.entry))
        horizon = float(
            self.entry.options.get(CONF_FORECAST_HORIZON_HOURS, DEFAULT_FORECAST_HORIZON_HOURS)
        )
        run_dirs = sorted((p for p in self.storage_dir.iterdir() if p.is_dir()), reverse=True)
        for run_dir in run_dirs:
            manifest_path = run_dir / self.MANIFEST_NAME
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text())
            except (ValueError, OSError):
                continue
            # Older manifests lack newer artifacts (e.g. field grids) -> skip so
            # the run is re-processed by the current code.
            if manifest.get("manifest_version", 1) < self.MANIFEST_VERSION:
                continue
            # A changed custom colour scale means the cached PNGs are stale ->
            # skip so the run is re-rendered with the new colours.
            if manifest.get("color_scales", "") != self._color_scales_signature():
                continue
            # A parameter switched on since this run was rendered isn't in it ->
            # skip so the run is processed again, now including that parameter.
            # (Every enabled parameter gets a key, even one that came out empty.)
            cached = manifest.get("frames", {})
            if not enabled <= set(cached):
                continue
            # Rendered for a shorter horizon than is now asked for -> process the
            # run again, or the card would stay short until the next run. (A
            # longer one is simply cut; a manifest from before 0.35 has no record
            # and is taken as it is.)
            cached_horizon = manifest.get("horizon_hours")
            if cached_horizon is not None and float(cached_horizon) < horizon:
                continue
            frames: dict[str, list[Frame]] = {}
            valid = True
            for key, flist in cached.items():
                if key not in enabled:
                    continue  # switched off since: don't offer it
                frames[key] = []
                for fd in flist:
                    valid_time = datetime.fromisoformat(fd["valid_time"])
                    run_time = datetime.fromisoformat(fd["run_time"])
                    if valid_time - run_time > timedelta(hours=horizon):
                        continue
                    png_path = run_dir / fd["png"]
                    if not png_path.exists():
                        valid = False
                        break
                    legend = render.Legend(
                        unit=fd["legend"]["unit"],
                        min_value=fd["legend"]["min_value"],
                        max_value=fd["legend"]["max_value"],
                        stops=tuple(fd["legend"]["stops"]),
                    )
                    def _opt(name: str) -> Path | None:
                        val = fd.get(name)
                        path = run_dir / val if val else None
                        return path if path and path.exists() else None

                    frames[key].append(
                        Frame(
                            parameter_key=key,
                            valid_time=valid_time,
                            run_time=run_time,
                            png_path=png_path,
                            bounds=tuple(fd["bounds"]),
                            legend=legend,
                            wind_path=_opt("wind"),
                            field_path=_opt("field"),
                        )
                    )
                if not valid:
                    break
            if valid and any(frames.values()):
                return manifest.get("run_filename"), frames
        return None, {}

    def _cleanup_old_runs(self) -> None:
        retain = self.entry.options.get(CONF_RETAIN_RUNS, DEFAULT_RETAIN_RUNS)
        # The default cache is in no backup folder, but a storage_path may point
        # into one, and this is the one place that deletes from it in bulk. A
        # backup may have started during the decode, after the check that let
        # this run through -- so re-check right before removing anything. The
        # stale run is simply dropped after the next run instead.
        if self.backup_in_progress() or not self.storage_dir.exists():
            return
        run_dirs = sorted((p for p in self.storage_dir.iterdir() if p.is_dir()), reverse=True)
        for stale_dir in run_dirs[retain:]:
            shutil.rmtree(stale_dir, ignore_errors=True)

    def get_frame(self, parameter_key: str, frame_id: str) -> Frame | None:
        for frame in self.frames.get(parameter_key, []):
            if frame.png_path.stem == frame_id:
                return frame
        return None
