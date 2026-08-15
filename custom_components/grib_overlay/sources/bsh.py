"""BSH ocean-current source: North Sea surface currents from the BSH model.

The Bundesamt fuer Seeschifffahrt und Hydrographie publishes surface-current
forecasts on a free, anonymous FTP server (no key). The "no" (Nordsee) area
covers the whole North Sea -- including the Dutch, Belgian and (northern)
French coasts -- as GRIB1 (u/v current components) on a regular ~5.5 km lat/lon
grid.

Unlike KNMI/DWD, one BSH file bundles a whole 24-hour block at 15-minute steps
(96 time steps of u+v). We split it on download into one small GRIB file per
time step (copying the raw message bytes, no re-encoding), so the rest of the
pipeline treats each step as an ordinary single-time vector member.

FTP is blocking (ftplib), so all network I/O runs in an executor.
"""

from __future__ import annotations

import asyncio
import bz2
import ftplib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import grib1
from .base import (
    GribDatasetInfo,
    GribFileInfo,
    GribParameter,
    GribSource,
    GribSourceError,
)

_HOST = "ftp.bsh.de"
_DIR = "/outgoing/Stroemungsvorhersagen/grib1/Nordsee"
_AREA = "no"  # whole North Sea (covers the NL/BE/FR coast); ~5.5 km

# One VV block spans 24 h of 15-minute steps.
_BLOCK_HOURS = 24

_CURRENT = GribParameter(
    key="current",
    name="Zeestroming (oppervlak)",
    unit="m/s",
    kind="vector",
    grib_filter_u={"indicatorOfParameter": 49, "indicatorOfTypeOfLevel": 160, "level": 1},
    grib_filter_v={"indicatorOfParameter": 50, "indicatorOfTypeOfLevel": 160, "level": 1},
    colormap="current",
    value_range=(0, 2.5),
)

KNOWN_DATASETS: tuple[GribDatasetInfo, ...] = (
    GribDatasetInfo(
        key="bsh_current_northsea",
        name="BSH - Zeestroming Noordzee (NL/BE/FR-kust)",
        version="1.0",
        description=(
            "15-minuten oppervlakte-zeestroming (u/v) voor de hele Noordzee incl. "
            "de Nederlandse, Belgische en noord-Franse kust, regulier lat-lon grid "
            "(~5,5 km). Bron: BSH, open FTP, geen sleutel."
        ),
        grid_type="regular_latlon",
        bounds=(48.625, -3.875, 60.625, 8.875),
        output_frequency_hours=0.25,
        forecast_horizon_hours=48,
        parameters=(_CURRENT,),
    ),
)

_FILE_RE = re.compile(rf"Current_{_AREA}_(\d{{10}})_(\d+)\.grb\.bz2")


def _valid_dt(data_date: int, data_time: int) -> datetime:
    y, m, d = data_date // 10000, (data_date // 100) % 100, data_date % 100
    return datetime(y, m, d, data_time // 100, data_time % 100, tzinfo=timezone.utc)


def _run_dt(run_id: str) -> datetime:
    return datetime.strptime(run_id, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def _run_day(run_id: str) -> datetime:
    return _run_dt(run_id).replace(hour=0, minute=0, second=0, microsecond=0)


def _plan_blocks(
    run_id: str, available: dict[str, set[int]], horizon_hours: float
) -> list[tuple[str, int]]:
    """Pick the (run, block) files to download to cover ``[run, run+horizon]``.

    BSH numbers each ``.grb.bz2`` block by forecast *day*: block ``vv`` of a run
    spans the calendar day ``run_date + vv``. The newest run can be published out
    of order and is sometimes momentarily missing its near-term (today) block,
    while the *previous* run still serves that day. So for every calendar day in
    the window we take the block from the newest run that actually has it
    (preferring the requested run), and simply skip a day that no run covers --
    instead of assuming blocks start at 0 and aborting at the first gap.
    """
    target = _run_dt(run_id)
    window_end = target + timedelta(hours=horizon_hours)
    candidates = [run_id] + sorted((r for r in available if r != run_id), reverse=True)
    plan: list[tuple[str, int]] = []
    day = _run_day(run_id)
    while day < window_end:
        day_end = day + timedelta(days=1)
        if day_end > target:  # this calendar day overlaps the forecast window
            for rid in candidates:
                vv = (day - _run_day(rid)).days
                if vv >= 0 and vv in available.get(rid, set()):
                    plan.append((rid, vv))
                    break
        day = day_end
    return plan


class BshSource(GribSource):
    """GribSource for BSH's open FTP North Sea current forecasts (GRIB1)."""

    key = "bsh"
    name = "BSH (zeestroming Noordzee)"
    supports_push_notifications = False
    provides_archive = False

    def __init__(self, session=None, api_key: str | None = None,
                 notification_api_key: str | None = None, instance_id: str | None = None) -> None:
        pass  # anonymous FTP: no session, key or push

    async def async_list_datasets(self) -> list[GribDatasetInfo]:
        return list(KNOWN_DATASETS)

    def _list_runs(self) -> set[str]:
        try:
            with ftplib.FTP(_HOST, timeout=30) as ftp:
                ftp.login()
                names = ftp.nlst(_DIR)
        except (ftplib.all_errors, OSError) as err:  # type: ignore[misc]
            raise GribSourceError(f"BSH FTP listing failed: {err}") from err
        return {m.group(1) for n in names if (m := _FILE_RE.search(n))}

    async def async_list_files(
        self, dataset: GribDatasetInfo, *, max_keys: int = 20,
        order_by: str = "lastModified", sorting: str = "desc",
    ) -> list[GribFileInfo]:
        runs = await asyncio.get_running_loop().run_in_executor(None, self._list_runs)
        if not runs:
            return []
        latest = max(runs)
        run_dt = datetime.strptime(latest, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        return [GribFileInfo(filename=latest, size=0, last_modified=run_dt.isoformat())]

    async def async_download_file(self, dataset, filename, destination) -> Path:
        raise GribSourceError("BSH delivers per-time files; use async_download_run")

    def _download_split(self, run_id: str, run_dir: Path, horizon_hours: float) -> list[Path]:
        target = _run_dt(run_id)
        window_end = target + timedelta(hours=horizon_hours)
        run_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        seen: set[tuple[int, int]] = set()  # dedupe valid times when runs overlap
        try:
            with ftplib.FTP(_HOST, timeout=60) as ftp:
                ftp.login()
                # Which blocks each run actually publishes -- BSH omits/reorders them.
                available: dict[str, set[int]] = {}
                for name in ftp.nlst(_DIR):
                    if (m := _FILE_RE.search(name)):
                        available.setdefault(m.group(1), set()).add(int(m.group(2)))
                for source_run, vv in _plan_blocks(run_id, available, horizon_hours):
                    fn = f"Current_{_AREA}_{source_run}_{vv:02d}.grb.bz2"
                    chunks = bytearray()
                    try:
                        ftp.retrbinary(f"RETR {_DIR}/{fn}", chunks.extend)
                    except ftplib.error_perm:
                        continue  # block vanished between listing and fetch; skip the gap
                    raw = bz2.decompress(bytes(chunks))
                    # Group the raw records by valid time, keep those in the window.
                    groups: dict[tuple[int, int], bytearray] = {}
                    for rec, ddate, dtime in grib1.iter_records(raw):
                        groups.setdefault((ddate, dtime), bytearray()).extend(rec)
                    for (ddate, dtime), rec_bytes in groups.items():
                        if (ddate, dtime) in seen:
                            continue
                        valid = _valid_dt(ddate, dtime)
                        if valid < target or valid > window_end:
                            continue
                        seen.add((ddate, dtime))
                        dest = run_dir / f"current_{ddate:08d}{dtime:04d}.grib"
                        dest.write_bytes(bytes(rec_bytes))
                        paths.append(dest)
        except (ftplib.all_errors, OSError) as err:  # type: ignore[misc]
            raise GribSourceError(f"BSH FTP download failed: {err}") from err
        return paths

    async def async_download_run(
        self, dataset, run_id, run_dir, param_keys, horizon_hours,
    ) -> list[Path]:
        return await asyncio.get_running_loop().run_in_executor(
            None, self._download_split, run_id, run_dir, horizon_hours
        )
