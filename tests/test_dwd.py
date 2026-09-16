"""Offline tests for the DWD source's run discovery + directory parsing.

The actual downloads are exercised against the live opendata.dwd.de server
during development; here we only unit-test the filename/run parsing with a fake
HTTP session so it runs without network.
"""

from __future__ import annotations

import bz2

import pytest

from custom_components.grib_overlay.sources.base import GribSourceError
from custom_components.grib_overlay.sources.dwd import (
    _BASE,
    _EWAM_DIR,
    _ICON_D2_BASE,
    _ICON_D2_DIRS,
    _ICON_D2_RUN_HOURS,
    KNOWN_DATASETS,
    DwdSource,
)

EWAM = next(d for d in KNOWN_DATASETS if d.key == "ewam")
ICON_D2 = next(d for d in KNOWN_DATASETS if d.key == "icon_d2")


class _FakeResp:
    def __init__(self, body, status: int) -> None:
        self._body, self.status = body, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self) -> str:
        return self._body

    async def read(self) -> bytes:
        return self._body


class _FakeSession:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages

    def get(self, url: str):
        return _FakeResp(self._pages.get(url, ""), 200 if url in self._pages else 404)


def _listing(run: str, steps: range) -> str:
    return "".join(
        f'<a href="EWAM_SWH_{run}_{s:03d}.grib2.bz2">x</a>' for s in steps
    )


@pytest.mark.asyncio
async def test_lists_latest_run() -> None:
    pages = {
        f"{_BASE}/00/swh/": _listing("2026072300", range(0, 79)),
        f"{_BASE}/12/swh/": _listing("2026072312", range(0, 79)),
    }
    src = DwdSource(_FakeSession(pages))
    files = await src.async_list_files(EWAM)
    assert len(files) == 1
    # 12Z run is newer than the same day's 00Z run.
    assert files[0].filename == "2026072312"
    assert files[0].last_modified.startswith("2026-07-23T12:00")


@pytest.mark.asyncio
async def test_a_run_still_being_published_is_not_listed() -> None:
    """DWD publishes an EWAM run over ~35 minutes. A poll that lands at the
    start used to take the run with a single file -- and, since a run is
    processed once, keep that one frame for 12 hours."""
    pages = {
        f"{_BASE}/00/swh/": _listing("2026091600", range(0, 1)),  # just started
        f"{_BASE}/12/swh/": _listing("2026091512", range(0, 79)),  # yesterday, complete
    }
    src = DwdSource(_FakeSession(pages))
    files = await src.async_list_files(EWAM)
    assert [f.filename for f in files] == ["2026091512"]


@pytest.mark.asyncio
async def test_ewam_refuses_a_run_with_a_parameter_still_missing(monkeypatch, tmp_path) -> None:
    run = "2026091600"
    pages = {
        f"{_BASE}/00/swh/": _listing(run, range(0, 79)),
        f"{_BASE}/12/swh/": "",
        # mwd trails swh by a few seconds per lead time.
        f"{_BASE}/00/mwd/": "".join(
            f'<a href="EWAM_MWD_{run}_{s:03d}.grib2.bz2">x</a>' for s in range(0, 40)
        ),
        f"{_BASE}/12/mwd/": "",
    }
    src = DwdSource(_FakeSession(pages))
    fetched: list = []

    async def _fake_dl(urls, dest, loop):
        fetched.append(dest)

    monkeypatch.setattr(src, "_download_bunzip", _fake_dl)
    with pytest.raises(GribSourceError, match="not complete"):
        await src.async_download_run(
            EWAM, run, tmp_path, ["wave_height", "wave_direction"], horizon_hours=60
        )
    assert fetched == []


@pytest.mark.asyncio
async def test_horizon_limits_downloaded_steps(monkeypatch, tmp_path) -> None:
    run = "2026072312"
    pages = {
        f"{_BASE}/12/swh/": _listing(run, range(0, 6)),
        f"{_BASE}/00/swh/": "",
    }
    src = DwdSource(_FakeSession(pages))

    grabbed: list[int] = []

    async def _fake_dl(urls, dest, loop):
        grabbed.append(int(dest.stem.rsplit("_", 1)[1]))
        dest.write_bytes(b"x")

    monkeypatch.setattr(src, "_download_bunzip", _fake_dl)
    paths = await src.async_download_run(
        EWAM, run, tmp_path, ["wave_height"], horizon_hours=3
    )
    # steps 0..3 only (horizon 3h), not 4/5.
    assert sorted(grabbed) == [0, 1, 2, 3]
    assert len(paths) == 4


def test_every_parameter_has_a_server_directory() -> None:
    """A parameter without a directory would silently never be downloaded."""
    assert {p.key for p in EWAM.parameters} == set(_EWAM_DIR)
    assert {p.key for p in ICON_D2.parameters} == set(_ICON_D2_DIRS)


@pytest.mark.asyncio
async def test_swell_comes_from_its_own_directory(monkeypatch, tmp_path) -> None:
    run = "2026091612"
    pages = {
        f"{_BASE}/12/shts/": "".join(
            f'<a href="EWAM_SHTS_{run}_{s:03d}.grib2.bz2">x</a>' for s in range(3)
        ),
        f"{_BASE}/00/shts/": "",
    }
    src = DwdSource(_FakeSession(pages))
    urls: list[str] = []

    async def _fake_dl(got, dest, loop):
        urls.extend(got)
        dest.write_bytes(b"x")

    monkeypatch.setattr(src, "_download_bunzip", _fake_dl)
    await src.async_download_run(EWAM, run, tmp_path, ["swell_height"], horizon_hours=2)
    assert urls == [f"{_BASE}/12/shts/EWAM_SHTS_{run}_{s:03d}.grib2.bz2" for s in range(3)]


def _d2_name(run: str, step: int, dwd_dir: str) -> str:
    return f"icon-d2_germany_regular-lat-lon_single-level_{run}_{step:03d}_2d_{dwd_dir}.grib2.bz2"


def _d2_listing(dwd_dir: str, *runs: tuple[str, range]) -> str:
    """An Apache index as DWD serves it: the link text is truncated, and the
    icosahedral twin of every file sits next to the regular-lat-lon one."""
    rows = []
    for run, steps in runs:
        for s in steps:
            rows.append(f'<a href="{_d2_name(run, s, dwd_dir)}">icon-d2_germany_regular-lat-lon_si..&gt;</a>')
            rows.append(
                f'<a href="icon-d2_germany_icosahedral_single-level_{run}_{s:03d}_2d_{dwd_dir}.grib2.bz2">x</a>'
            )
    return "\n".join(rows)


@pytest.mark.asyncio
async def test_icon_d2_picks_the_newest_complete_run() -> None:
    """A run still being published shares its directory with yesterday's run of
    the same hour; neither the half-published run nor the old one may win over
    the newest complete run."""
    full = range(0, 49)
    pages = {f"{_ICON_D2_BASE}/{hh}/t_2m/": _d2_listing("t_2m", (f"20260916{hh}", full))
             for hh in _ICON_D2_RUN_HOURS}
    pages[f"{_ICON_D2_BASE}/18/t_2m/"] = _d2_listing(
        "t_2m", ("2026091518", range(3, 49)), ("2026091618", range(0, 3))
    )
    pages[f"{_ICON_D2_BASE}/21/t_2m/"] = _d2_listing("t_2m", ("2026091521", full))
    src = DwdSource(_FakeSession(pages))
    files = await src.async_list_files(ICON_D2)
    assert [f.filename for f in files] == ["2026091615"]
    assert files[0].last_modified.startswith("2026-09-16T15:00")


@pytest.mark.asyncio
async def test_icon_d2_joins_u_and_v_and_keeps_lead_time_order(tmp_path) -> None:
    run = "2026091612"
    pages: dict = {}
    for dwd_dir, tag in (("u_10m", b"U"), ("v_10m", b"V"), ("tot_prec", b"P")):
        pages[f"{_ICON_D2_BASE}/12/{dwd_dir}/"] = _d2_listing(dwd_dir, (run, range(0, 49)))
        for s in range(0, 49):
            pages[f"{_ICON_D2_BASE}/12/{dwd_dir}/{_d2_name(run, s, dwd_dir)}"] = bz2.compress(
                tag + str(s).encode()
            )
    src = DwdSource(_FakeSession(pages))
    paths = await src.async_download_run(
        ICON_D2, run, tmp_path, ["precipitation", "wind_10m"], horizon_hours=2
    )
    # Per parameter, ascending lead time: the precipitation de-accumulation
    # depends on it.
    assert [p.name for p in paths] == [
        "precipitation_000.grib2", "precipitation_001.grib2", "precipitation_002.grib2",
        "wind_10m_000.grib2", "wind_10m_001.grib2", "wind_10m_002.grib2",
    ]
    assert (tmp_path / "wind_10m_001.grib2").read_bytes() == b"U1V1"
    assert (tmp_path / "precipitation_002.grib2").read_bytes() == b"P2"


@pytest.mark.asyncio
async def test_icon_d2_refuses_a_run_that_is_still_publishing(monkeypatch, tmp_path) -> None:
    run = "2026091618"
    pages = {
        f"{_ICON_D2_BASE}/18/t_2m/": _d2_listing("t_2m", (run, range(0, 49))),
        # t_2m is done, but relhum_2m is still at +5h.
        f"{_ICON_D2_BASE}/18/relhum_2m/": _d2_listing("relhum_2m", (run, range(0, 6))),
    }
    src = DwdSource(_FakeSession(pages))
    fetched: list = []

    async def _fake_dl(urls, dest, loop):
        fetched.append(dest)

    monkeypatch.setattr(src, "_download_bunzip", _fake_dl)
    with pytest.raises(GribSourceError, match="not complete"):
        await src.async_download_run(
            ICON_D2, run, tmp_path, ["temperature_2m", "humidity_2m"], horizon_hours=24
        )
    assert fetched == []  # nothing downloaded before the run is complete
