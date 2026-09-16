"""Offline tests for the DMI source: run discovery, lead times, partial downloads.

The live API (opendataapi.dmi.dk) and its files were checked during
development; here a fake session stands in for both.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.grib_overlay.sources import dmi
from custom_components.grib_overlay.sources.base import GribSourceError
from custom_components.grib_overlay.sources.dmi import KNOWN_DATASETS, DmiSource

WAM = next(d for d in KNOWN_DATASETS if d.key == "dmi_wam_nsb")
DKSS = next(d for d in KNOWN_DATASETS if d.key == "dmi_dkss_nsbs")


def _grib1(param: int, level_type: int, level: int, payload: bytes = b"x" * 20) -> bytes:
    """Just enough of a GRIB1 message for the source: length + PDS keys."""
    pds = bytearray(28)
    pds[8], pds[9] = param, level_type
    pds[10:12] = level.to_bytes(2, "big")
    body = bytes(pds) + payload + b"7777"
    return b"GRIB" + (8 + len(body)).to_bytes(3, "big") + bytes([1]) + body


class _Content:
    def __init__(self, body: bytes, chunk: int, log: list) -> None:
        self._body, self._chunk, self._log = body, chunk, log

    async def iter_chunked(self, size: int):
        for i in range(0, len(self._body), self._chunk):
            self._log.append(i + self._chunk)
            yield self._body[i:i + self._chunk]


class _Resp:
    def __init__(self, status: int, body, chunk: int, log: list) -> None:
        self.status = status
        self._body = body
        self.content = _Content(body if isinstance(body, bytes) else b"", chunk, log)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        return self._body


class _Session:
    def __init__(self, pages: dict, chunk: int = 7) -> None:
        self.pages, self.chunk, self.requested, self.read_up_to = pages, chunk, [], []

    def get(self, url: str):
        self.requested.append(url)
        if url not in self.pages:
            # Like the real API: an unknown run is an empty collection, a
            # missing file a 404.
            if "/items?" in url:
                return _Resp(200, {"features": []}, self.chunk, self.read_up_to)
            return _Resp(404, b"", self.chunk, self.read_up_to)
        return _Resp(200, self.pages[url], self.chunk, self.read_up_to)


def _items(run: datetime, leads) -> dict:
    return {
        "features": [
            {
                "properties": {
                    "modelRun": run.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "datetime": (run + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                "asset": {"data": {"href": f"https://files/{run:%Y%m%d%H}_{h:03d}.grib"}},
            }
            for h in leads
        ]
    }


def _items_url(dataset, run: datetime) -> str:
    return (
        f"{dmi.API_BASE_URL}/{dmi._COLLECTION[dataset.key]}/items"
        f"?modelRun={run:%Y-%m-%dT%H:%M:%SZ}&limit=1000"
    )


def _now_run() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=now.hour - now.hour % 6, minute=0, second=0, microsecond=0)


@pytest.mark.asyncio
async def test_picks_the_newest_run_that_is_complete() -> None:
    newest = _now_run()
    previous = newest - timedelta(hours=6)
    session = _Session({
        _items_url(WAM, newest): _items(newest, range(0, 40)),  # still publishing
        _items_url(WAM, previous): _items(previous, range(0, 133)),
    })
    src = DmiSource(session)
    files = await src.async_list_files(WAM)
    assert [f.filename for f in files] == [f"{previous:%Y%m%d%H}"]

    # The complete run is remembered: the next poll only re-checks newer runs.
    session.requested.clear()
    await src.async_list_files(WAM)
    assert session.requested == [_items_url(WAM, newest)]


@pytest.mark.asyncio
async def test_no_complete_run_lists_nothing() -> None:
    src = DmiSource(_Session({}))
    assert await src.async_list_files(DKSS) == []


@pytest.mark.asyncio
async def test_downloads_the_leads_within_the_horizon_in_order(tmp_path) -> None:
    run = _now_run() - timedelta(hours=6)
    pages = {_items_url(WAM, run): _items(run, range(0, 133))}
    wave = _grib1(229, 102, 0)
    for h in range(0, 133):
        pages[f"https://files/{run:%Y%m%d%H}_{h:03d}.grib"] = _grib1(245, 102, 0) + wave
    src = DmiSource(_Session(pages))
    paths = await src.async_download_run(
        WAM, f"{run:%Y%m%d%H}", tmp_path, ["wave_height"], horizon_hours=3
    )
    assert [p.name for p in paths] == [f"{run:%Y%m%d%H}_{h:03d}.grib" for h in range(4)]
    # Only the wanted field is kept.
    assert paths[0].read_bytes() == wave


@pytest.mark.asyncio
async def test_dkss_stops_reading_once_the_surface_fields_are_in(tmp_path) -> None:
    """A DKSS file is ~9 MB of depth levels behind ~0.6 MB of surface fields."""
    run = _now_run() - timedelta(hours=6)
    surface = [_grib1(82, 1, 0), _grib1(49, 1, 0), _grib1(50, 1, 0)]
    depths = b"".join(_grib1(49, 160, lv, b"y" * 400) for lv in range(4, 40))
    url = f"https://files/{run:%Y%m%d%H}_000.grib"
    session = _Session({_items_url(DKSS, run): _items(run, [0]), url: b"".join(surface) + depths})
    src = DmiSource(session)
    (path,) = await src.async_download_run(
        DKSS, f"{run:%Y%m%d%H}", tmp_path, ["current", "water_level"], horizon_hours=0
    )
    assert path.read_bytes() == b"".join(surface)
    # Messages split across 7-byte chunks were reassembled, and the depth
    # levels behind them were never read.
    assert max(session.read_up_to) < len(b"".join(surface)) + 7 + 1


@pytest.mark.asyncio
async def test_a_file_without_the_wanted_fields_fails(tmp_path) -> None:
    run = _now_run() - timedelta(hours=6)
    url = f"https://files/{run:%Y%m%d%H}_000.grib"
    session = _Session({_items_url(WAM, run): _items(run, [0]), url: _grib1(245, 102, 0)})
    src = DmiSource(session)
    with pytest.raises(GribSourceError):
        await src.async_download_run(
            WAM, f"{run:%Y%m%d%H}", tmp_path, ["wave_height"], horizon_hours=0
        )


def test_every_parameter_has_a_filter_the_download_can_use() -> None:
    for dataset in KNOWN_DATASETS:
        keys = dmi._wanted_keys(list(dataset.parameters))
        assert keys and all(len(k) == 3 for k in keys)
