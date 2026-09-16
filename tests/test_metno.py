"""MET Norway source: per-lead splitting of files whose messages carry their valid time."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from custom_components.grib_overlay import grib_decode
from custom_components.grib_overlay.sources import metno
from custom_components.grib_overlay.sources.base import GribSourceError
from custom_components.grib_overlay.sources.metno import KNOWN_DATASETS, MetnoSource
from tests.test_grib1 import _make_grib1

OSLO = next(d for d in KNOWN_DATASETS if d.key == "metno_oslofjord")


def _at(message: bytes, day: int, hour: int, param: int | None = None) -> bytes:
    """A test message moved to 2026-09-<day> <hour>:00 as its reference time, P1 = 0."""
    out = bytearray(message)
    out[8 + 14], out[8 + 15], out[8 + 18] = day, hour, 0
    if param is not None:
        out[8 + 8] = param
    return bytes(out)


def _file(hours: list[tuple[int, int]], params=(33, 61)) -> bytes:
    base = _make_grib1(param=33, level=0, bits=4, raw_values=range(6))
    return b"".join(_at(base, d, h, p) for d, h in hours for p in params)


def test_split_rewrites_the_run_and_lead(tmp_path) -> None:
    buf = _file([(16, 22), (16, 23), (17, 0), (16, 21)])  # out of order on purpose
    paths = metno.split_by_lead(buf, "weather", tmp_path, horizon_hours=48)
    assert [p.name for p in paths] == [f"weather_{h:03d}.grib" for h in range(4)]
    run = datetime(2026, 9, 16, 21, tzinfo=timezone.utc)
    for lead, path in enumerate(paths):
        valid, member_run = grib_decode.peek_valid_time(path)
        assert member_run == run
        assert (valid - run).total_seconds() == lead * 3600


def test_first_hour_precipitation_placeholder_is_dropped(tmp_path) -> None:
    buf = _file([(16, 0), (16, 1)], params=(33, 61))
    first, second = metno.split_by_lead(buf, "weather", tmp_path, horizon_hours=48)
    assert metno._key(first.read_bytes()[:40])[0] == 33
    assert len(first.read_bytes()) * 2 == len(second.read_bytes())


def test_split_respects_the_horizon(tmp_path) -> None:
    buf = _file([(16, h) for h in range(6)], params=(49,))
    paths = metno.split_by_lead(buf, "current", tmp_path, horizon_hours=2)
    assert [p.name for p in paths] == ["current_000.grib", "current_001.grib", "current_002.grib"]


def test_long_leads_use_two_octets() -> None:
    base = _make_grib1(param=49, level=0, bits=4, raw_values=range(6))
    run = datetime(2026, 9, 16, 0, tzinfo=timezone.utc)
    patched = metno._with_run_time(base, run, 300)
    assert patched[8 + 20] == 10 and patched[8 + 18] * 256 + patched[8 + 19] == 300


def test_a_file_without_messages_fails(tmp_path) -> None:
    with pytest.raises(GribSourceError):
        metno.split_by_lead(b"<html>blocked</html>", "weather", tmp_path, horizon_hours=48)


class _Resp:
    def __init__(self, status: int, body: bytes) -> None:
        self.status, self._body = status, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self) -> bytes:
        return self._body


class _Session:
    def __init__(self, pages: dict[str, bytes], status: int = 200) -> None:
        self.pages, self.status, self.calls = pages, status, []

    def get(self, url: str, headers=None, timeout=None):
        self.calls.append((url, headers))
        return _Resp(self.status, self.pages.get(url, b""))


def _available(content: str, updated: dict[str, str]) -> bytes:
    return json.dumps([
        {"params": {"area": area, "content": content}, "updated": when}
        for area, when in updated.items()
    ]).encode()


@pytest.mark.asyncio
async def test_run_is_the_latest_update_of_the_area() -> None:
    base = metno.API_BASE_URL
    session = _Session({
        f"{base}/available.json?content=weather": _available("weather", {
            "oslofjord": "2026-09-16T20:03:43Z", "skagerrak": "2026-09-16T21:00:00Z"}),
        f"{base}/available.json?content=waves": _available("waves", {"oslofjord": "2026-09-16T15:42:14Z"}),
        f"{base}/available.json?content=current": _available("current", {"oslofjord": "2026-09-16T06:48:23Z"}),
    })
    files = await MetnoSource(session).async_list_files(OSLO)
    assert [f.filename for f in files] == ["20260916200343"]
    # Every request identifies the integration, as api.met.no requires.
    for _, headers in session.calls:
        assert headers["User-Agent"].startswith("ha-grib-weather-overlay/")
        assert metno.PROJECT_URL in headers["User-Agent"]


@pytest.mark.asyncio
async def test_downloads_only_the_contents_the_parameters_need(tmp_path) -> None:
    base = metno.API_BASE_URL
    session = _Session({
        f"{base}/?area=oslofjord&content=current": _file([(16, 0), (16, 1)], params=(49, 50)),
    })
    paths = await MetnoSource(session).async_download_run(
        OSLO, "20260916064823", tmp_path, ["current"], horizon_hours=24
    )
    assert [url for url, _ in session.calls] == [f"{base}/?area=oslofjord&content=current"]
    assert [p.name for p in paths] == ["current_000.grib", "current_001.grib"]


@pytest.mark.asyncio
async def test_forbidden_explains_the_user_agent_rule() -> None:
    with pytest.raises(GribSourceError, match="User-Agent"):
        await MetnoSource(_Session({}, status=403)).async_list_files(OSLO)


def test_every_parameter_maps_to_a_content() -> None:
    for dataset in KNOWN_DATASETS:
        assert {p.key for p in dataset.parameters} == set(metno._CONTENT_OF)
