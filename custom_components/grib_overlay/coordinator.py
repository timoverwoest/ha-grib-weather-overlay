"""Keeps cached GRIB overlay frames up to date for one config entry.

On each poll: ask the source for the latest run's filename. If it changed
since last time, download the run (a single archive containing one GRIB file
per lead time for KNMI), extract only the lead times inside the configured
forecast horizon, decode+render the enabled parameters for each of those,
cache the resulting PNGs on disk, and drop everything else (the archive
itself, members outside the horizon, and older runs beyond the retention
count) to keep bandwidth/disk bounded -- a HARMONIE run archive is roughly
850MB for ~49 lead times, far more than a home server should keep around.
"""

from __future__ import annotations

import logging
import shutil
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import grib_decode, render
from .const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_FORECAST_HORIZON_HOURS,
    CONF_PARAMETERS,
    CONF_RETAIN_RUNS,
    CONF_SOURCE,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_FORECAST_HORIZON_HOURS,
    DEFAULT_RETAIN_RUNS,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)
from .sources.base import GribDatasetInfo, GribParameter, GribSource, GribSourceError
from .sources.registry import get_source_class

_LOGGER = logging.getLogger(__name__)


@dataclass
class Frame:
    parameter_key: str
    valid_time: datetime
    run_time: datetime
    png_path: Path
    bounds: tuple[float, float, float, float]
    legend: render.Legend


class GribOverlayCoordinator(DataUpdateCoordinator[dict]):
    """One coordinator per config entry; owns one source + one dataset."""

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
        self.source: GribSource = source_cls(session, entry.data[CONF_API_KEY])
        self.storage_dir = Path(hass.config.path(DOMAIN, entry.entry_id))
        self._current_run_filename: str | None = None
        # frames[parameter_key] = list[Frame] sorted by valid_time
        self.frames: dict[str, list[Frame]] = {}

    async def _async_setup(self) -> None:
        """Called once before the first refresh: start push notifications if supported.

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
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict:
        try:
            datasets = await self.source.async_list_datasets()
        except GribSourceError as err:
            raise UpdateFailed(str(err)) from err

        dataset = next((d for d in datasets if d.key == self.entry.data[CONF_DATASET]), None)
        if dataset is None:
            raise UpdateFailed(f"Dataset '{self.entry.data[CONF_DATASET]}' not offered by source")

        try:
            files = await self.source.async_list_files(dataset, max_keys=1)
        except GribSourceError as err:
            raise UpdateFailed(str(err)) from err
        if not files:
            raise UpdateFailed("Source returned no files for this dataset")

        latest = files[0]
        if latest.filename != self._current_run_filename:
            _LOGGER.debug("New run detected for %s: %s", dataset.key, latest.filename)
            try:
                await self._process_new_run(dataset, latest.filename)
            except GribSourceError as err:
                raise UpdateFailed(str(err)) from err
            self._current_run_filename = latest.filename
            await self.hass.async_add_executor_job(self._cleanup_old_runs)

        return {"run_filename": self._current_run_filename, "dataset": dataset.key}

    async def _process_new_run(self, dataset: GribDatasetInfo, filename: str) -> None:
        enabled_keys = set(self.entry.data.get(CONF_PARAMETERS, []))
        parameters = [p for p in dataset.parameters if p.key in enabled_keys]
        if not parameters:
            _LOGGER.warning("No parameters enabled for %s, skipping run %s", dataset.key, filename)
            return

        horizon_hours = self.entry.options.get(
            CONF_FORECAST_HORIZON_HOURS, DEFAULT_FORECAST_HORIZON_HOURS
        )
        run_dir = self.storage_dir / Path(filename).stem
        tar_path = self.storage_dir / filename

        await self.source.async_download_file(dataset, filename, tar_path)
        try:
            new_frames = await self.hass.async_add_executor_job(
                self._extract_decode_and_render, tar_path, run_dir, parameters, horizon_hours
            )
        finally:
            await self.hass.async_add_executor_job(tar_path.unlink, True)

        self.frames = new_frames

    def _extract_decode_and_render(
        self,
        tar_path: Path,
        run_dir: Path,
        parameters: list[GribParameter],
        horizon_hours: float,
    ) -> dict[str, list[Frame]]:
        """Blocking: runs in the executor. Extracts, filters by horizon, decodes, renders."""
        run_dir.mkdir(parents=True, exist_ok=True)
        new_frames: dict[str, list[Frame]] = {p.key: [] for p in parameters}
        run_time: datetime | None = None

        with tarfile.open(tar_path, "r") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                extracted_path = run_dir / Path(member.name).name
                with tar.extractfile(member) as src, extracted_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

                try:
                    valid_time, member_run_time = grib_decode.peek_valid_time(extracted_path)
                except grib_decode.GribDecodeError as err:
                    _LOGGER.debug("Skipping unreadable member %s: %s", member.name, err)
                    extracted_path.unlink(missing_ok=True)
                    continue

                run_time = run_time or member_run_time
                if valid_time - member_run_time > timedelta(hours=horizon_hours):
                    extracted_path.unlink(missing_ok=True)
                    continue

                for parameter in parameters:
                    try:
                        field = grib_decode.decode_parameter(extracted_path, parameter)
                    except grib_decode.GribDecodeError as err:
                        _LOGGER.debug(
                            "Parameter %s not in member %s: %s", parameter.key, member.name, err
                        )
                        continue
                    frame_obj, legend = render.render_field(
                        field, colormap=parameter.colormap, value_range=parameter.value_range
                    )
                    png_path = run_dir / f"{parameter.key}_{field.valid_time:%Y%m%dT%H%M}.png"
                    png_path.write_bytes(frame_obj.png_bytes)
                    new_frames[parameter.key].append(
                        Frame(
                            parameter_key=parameter.key,
                            valid_time=field.valid_time,
                            run_time=field.run_time,
                            png_path=png_path,
                            bounds=frame_obj.bounds,
                            legend=legend,
                        )
                    )
                extracted_path.unlink(missing_ok=True)

        for frames in new_frames.values():
            frames.sort(key=lambda f: f.valid_time)
        return new_frames

    def _cleanup_old_runs(self) -> None:
        retain = self.entry.options.get(CONF_RETAIN_RUNS, DEFAULT_RETAIN_RUNS)
        if not self.storage_dir.exists():
            return
        run_dirs = sorted((p for p in self.storage_dir.iterdir() if p.is_dir()), reverse=True)
        for stale_dir in run_dirs[retain:]:
            shutil.rmtree(stale_dir, ignore_errors=True)

    def get_frame(self, parameter_key: str, frame_id: str) -> Frame | None:
        for frame in self.frames.get(parameter_key, []):
            if frame.png_path.stem == frame_id:
                return frame
        return None
