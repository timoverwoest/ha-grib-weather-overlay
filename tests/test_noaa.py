"""Offline tests for the NOAA source (GFS and GFS-Wave through NOMADS).

The real downloads are exercised against nomads.ncep.noaa.gov during
development; here a fake session covers the parts that are easy to get subtly
wrong: which lead times are asked for, which run counts as usable, and the
filters that pick one field out of a file holding all of them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from custom_components.grib_overlay.sources.base import GribSourceError
from custom_components.grib_overlay.sources.noaa import (
    _GFS_FIELDS,
    _GFS_WAVE_FIELDS,
    _HOURLY_TO,
    _LAST_STEP,
    _MODELS,
    _PROBE_STEP,
    KNOWN_DATASETS,
    NoaaSource,
    steps_within,
)

GFS = next(d for d in KNOWN_DATASETS if d.key == "gfs")
GFS_WAVE = next(d for d in KNOWN_DATASETS if d.key == "gfs_wave")


class _FakeResp:
    def __init__(self, body: bytes, status: int) -> None:
        self._body, self.status = body, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self) -> bytes:
        return self._body


class _FakeSession:
    """Answers with GRIB for the runs/steps it was given, 404 for the rest."""

    def __init__(self, available: dict[str, set[int]] | None = None) -> None:
        self.available = available if available is not None else {}
        self.requested: list[str] = []

    def get(self, url: str, timeout=None):
        self.requested.append(url)
        query = parse_qs(urlparse(url).query)
        # /gfs.20260922/00/atmos, or /gfs.20260922/00/wave/gridded
        date, hour = query["dir"][0].removeprefix("/gfs.").split("/")[:2]
        step = int(query["file"][0].split(".f")[1].removesuffix(".grib2"))
        if step in self.available.get(f"{date}{hour}", set()):
            return _FakeResp(b"GRIB\x00\x00", 200)
        return _FakeResp(b"<html>not found</html>", 404)


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query, keep_blank_values=True)


# -- lead times ---------------------------------------------------------------


def test_steps_are_hourly_then_three_hourly() -> None:
    assert steps_within(4) == [0, 1, 2, 3, 4]
    assert steps_within(_HOURLY_TO)[-1] == _HOURLY_TO
    beyond = steps_within(_HOURLY_TO + 10)
    assert beyond[_HOURLY_TO + 1 :] == [123, 126, 129]
    assert steps_within(1000)[-1] == _LAST_STEP


def test_the_horizon_caps_the_steps() -> None:
    """The dataset reaches +384 h, but nobody has to fetch all of it."""
    assert len(steps_within(24)) == 25
    assert max(steps_within(24)) == 24


# -- run discovery ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_newest_published_run_is_listed(monkeypatch) -> None:
    _freeze(monkeypatch, datetime(2026, 9, 22, 16, 40, tzinfo=timezone.utc))
    session = _FakeSession({"2026092212": {_PROBE_STEP}, "2026092206": {_PROBE_STEP}})
    files = await NoaaSource(session).async_list_files(GFS)
    assert [f.filename for f in files] == ["2026092212"]
    assert files[0].last_modified.startswith("2026-09-22T12:00")


@pytest.mark.asyncio
async def test_a_run_that_has_not_reached_the_probe_step_is_skipped(monkeypatch) -> None:
    """NCEP publishes a run lead time by lead time over a few hours. Taking one
    before it is usable would leave it in the cache nearly empty."""
    _freeze(monkeypatch, datetime(2026, 9, 22, 16, 40, tzinfo=timezone.utc))
    session = _FakeSession({"2026092212": {0, 1, 2}, "2026092206": {_PROBE_STEP}})
    files = await NoaaSource(session).async_list_files(GFS)
    assert [f.filename for f in files] == ["2026092206"]


@pytest.mark.asyncio
async def test_nothing_is_listed_when_no_run_is_published(monkeypatch) -> None:
    _freeze(monkeypatch, datetime(2026, 9, 22, 16, 40, tzinfo=timezone.utc))
    session = _FakeSession({})
    assert await NoaaSource(session).async_list_files(GFS) == []


@pytest.mark.asyncio
async def test_the_run_probe_asks_for_a_single_grid_cell(monkeypatch) -> None:
    """It runs at every poll, so it must not pull a whole field."""
    _freeze(monkeypatch, datetime(2026, 9, 22, 16, 40, tzinfo=timezone.utc))
    session = _FakeSession({"2026092212": {_PROBE_STEP}})
    await NoaaSource(session).async_list_files(GFS)
    query = _query(session.requested[0])
    assert float(query["rightlon"][0]) - float(query["leftlon"][0]) <= 0.5
    assert float(query["toplat"][0]) - float(query["bottomlat"][0]) <= 0.5
    assert query["var_UGRD"] == ["on"]
    assert "var_CAPE" not in query


# -- downloading --------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_member_per_lead_time_holds_every_parameter(tmp_path) -> None:
    """One request per lead time rather than one per parameter: the coordinator
    already reads a member that holds several parameters, and NOMADS is a free
    service that should be asked as little as possible."""
    session = _FakeSession({"2026092200": set(range(4))})
    paths = await NoaaSource(session).async_download_run(
        GFS, "2026092200", tmp_path, ["wind_10m", "pressure_msl"], horizon_hours=3
    )
    assert [p.name for p in paths] == [f"gfs_{s:03d}.grib2" for s in range(4)]
    assert len(session.requested) == 4
    query = _query(session.requested[0])
    assert query["var_UGRD"] == ["on"] and query["var_VGRD"] == ["on"]
    assert query["var_PRMSL"] == ["on"]
    assert "var_CAPE" not in query  # not enabled
    assert set(query["lev_10_m_above_ground"]) == {"on"}
    assert query["lev_mean_sea_level"] == ["on"]


@pytest.mark.asyncio
async def test_members_come_back_in_ascending_lead_time(tmp_path) -> None:
    session = _FakeSession({"2026092200": set(range(6))})
    paths = await NoaaSource(session).async_download_run(
        GFS, "2026092200", tmp_path, ["pressure_msl"], horizon_hours=5
    )
    steps = [int(p.stem.rsplit("_", 1)[1]) for p in paths]
    assert steps == sorted(steps) == [0, 1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_a_run_missing_a_lead_time_is_refused(tmp_path) -> None:
    """A run can be listed and still be short of a longer horizon; failing keeps
    it out of the cache with gaps in it, and the next poll retries."""
    session = _FakeSession({"2026092200": {0, 1}})
    with pytest.raises(GribSourceError, match="not complete"):
        await NoaaSource(session).async_download_run(
            GFS, "2026092200", tmp_path, ["pressure_msl"], horizon_hours=3
        )


@pytest.mark.asyncio
async def test_nothing_enabled_is_an_error_not_an_empty_run(tmp_path) -> None:
    session = _FakeSession({"2026092200": {0}})
    with pytest.raises(GribSourceError, match="No GFS parameters"):
        await NoaaSource(session).async_download_run(
            GFS, "2026092200", tmp_path, ["water_level"], horizon_hours=0
        )


@pytest.mark.asyncio
async def test_the_wave_model_asks_for_every_level(tmp_path) -> None:
    """Swell arrives split into partitions, each at its own level, so the wave
    request cannot name the levels it wants the way the weather one does."""
    session = _FakeSession({"2026092200": {0}})
    await NoaaSource(session).async_download_run(
        GFS_WAVE, "2026092200", tmp_path, ["swell_height"], horizon_hours=0
    )
    query = _query(session.requested[0])
    assert query["all_lev"] == ["on"]
    assert query["var_SWELL"] == ["on"]


@pytest.mark.asyncio
async def test_the_window_is_the_one_the_dataset_advertises(tmp_path) -> None:
    session = _FakeSession({"2026092200": {0}})
    await NoaaSource(session).async_download_run(
        GFS, "2026092200", tmp_path, ["pressure_msl"], horizon_hours=0
    )
    query = _query(session.requested[0])
    south, west, north, east = GFS.bounds
    assert [float(query[k][0]) for k in ("bottomlat", "leftlon", "toplat", "rightlon")] == [
        south,
        west,
        north,
        east,
    ]


# -- the filters --------------------------------------------------------------


def test_every_advertised_parameter_can_actually_be_fetched() -> None:
    for dataset in (GFS, GFS_WAVE):
        model = _MODELS[dataset.key]
        for parameter in dataset.parameters:
            field = model.field(parameter.key)
            assert field is not None, parameter.key
            assert field.variables, parameter.key


def test_weather_filters_pin_a_level_and_an_instantaneous_field() -> None:
    """A NOMADS response holds every parameter for one lead time, so category
    and number alone would match the same quantity at another level -- or the
    interval mean GFS publishes next to the value itself."""
    for field in _GFS_FIELDS:
        filters = [
            f
            for f in (
                field.parameter.grib_filter,
                field.parameter.grib_filter_u,
                field.parameter.grib_filter_v,
            )
            if f
        ]
        for grib_filter in filters:
            assert "indicatorOfTypeOfLevel" in grib_filter, field.parameter.key
            assert "level" in grib_filter, field.parameter.key
            assert grib_filter["productDefinitionTemplateNumber"] == 0, field.parameter.key


def test_swell_is_pinned_to_its_first_partition() -> None:
    swell = [f for f in _GFS_WAVE_FIELDS if f.parameter.key.startswith("swell_")]
    assert len(swell) == 3
    for field in swell:
        assert field.parameter.grib_filter["indicatorOfTypeOfLevel"] == 241
        assert field.parameter.grib_filter["level"] == 1.0


def test_the_wave_keys_are_the_shared_ones() -> None:
    """The comparison view lines models up by key, so GFS-Wave has to use the
    same vocabulary as EWAM and DMI."""
    from custom_components.grib_overlay.sources.base import direction_key_for

    keys = {p.key for p in GFS_WAVE.parameters}
    assert {"wave_height", "swell_height", "wind_wave_height"} <= keys
    for key in ("wave_height", "wave_peak_period", "swell_height", "wind_wave_height"):
        assert direction_key_for(key) in keys, key


def test_the_weather_keys_match_the_high_resolution_models() -> None:
    from custom_components.grib_overlay.sources.dwd import KNOWN_DATASETS as DWD

    icon = next(d for d in DWD if d.key == "icon_d2")
    assert {p.key for p in icon.parameters} <= {p.key for p in GFS.parameters}


def _freeze(monkeypatch, now: datetime) -> None:
    import custom_components.grib_overlay.sources.noaa as noaa

    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(noaa, "datetime", _Now)
