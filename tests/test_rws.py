"""Rijkswaterstaat (NOOS-Matroos) source, and the gridded member files it writes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest

from custom_components.grib_overlay import grib_decode, gridded
from custom_components.grib_overlay.sources import rws
from custom_components.grib_overlay.sources.base import GribParameter, GribSourceError
from custom_components.grib_overlay.sources.rws import KNOWN_DATASETS, RwsSource
from tests import nc3_writer

DCSM = next(d for d in KNOWN_DATASETS if d.key == "rws_dcsm")
RUN = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


def test_member_round_trip_through_grib_decode(tmp_path) -> None:
    lats, lons = np.array([51.0, 51.05]), np.array([3.0, 3.05, 3.1])
    sep = np.array([[0.1, 0.2, np.nan], [0.4, 0.5, 0.6]])
    path = tmp_path / "m.npz"
    gridded.write_member(
        path, fields={"sep": sep, "velu": sep * 2, "velv": sep * 0},
        lats=lats, lons=lons, valid_time=RUN + timedelta(hours=3), run_time=RUN,
    )
    valid, run = grib_decode.peek_valid_time(path)
    assert (valid, run) == (RUN + timedelta(hours=3), RUN)

    level = GribParameter(key="water_level", name="w", unit="m", grib_filter={"field": "sep"})
    field = grib_decode.decode_parameter(path, level)
    assert np.allclose(field.data, sep, equal_nan=True)
    assert field.lats.tolist() == lats.tolist() and field.lons.tolist() == lons.tolist()

    current = next(p for p in DCSM.parameters if p.key == "current")
    vec = grib_decode.decode_vector_components(path, current)
    assert np.allclose(vec.u, sep * 2, equal_nan=True)

    # A GRIB-style filter finds nothing in a member (and vice versa).
    grib_like = GribParameter(key="x", name="x", unit="m", grib_filter={"indicatorOfParameter": 82})
    with pytest.raises(grib_decode.GribDecodeError):
        grib_decode.decode_parameter(path, grib_like)


def test_member_axes_must_ascend(tmp_path) -> None:
    with pytest.raises(gridded.GriddedError):
        gridded.write_member(
            tmp_path / "m.npz", fields={"a": np.zeros((2, 2))},
            lats=np.array([52.0, 51.0]), lons=np.array([3.0, 4.0]),
            valid_time=RUN, run_time=RUN,
        )


def test_despike_masks_isolated_impossible_levels_only() -> None:
    grid = np.full((5, 5), 0.5)
    grid[:, 3:] = 1.8  # a real, smooth tidal gradient
    grid[2, 1] = 9.0  # a coastal cell the interpolation got wrong
    grid[0, 0] = np.nan
    out = rws.despike(grid, 2.0)
    assert np.isnan(out[2, 1])
    assert np.isnan(out).sum() == 2
    assert out[2, 4] == 1.8


def _matroos_nc(start: datetime, hours: list[int], fields=("sep", "velu", "velv")) -> bytes:
    y, x = np.array([51.0, 51.05, 51.1]), np.array([3.0, 3.05, 3.1])
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    minutes = np.array([((start + timedelta(hours=h)) - epoch).total_seconds() / 60 for h in hours])
    variables = [
        ("x", ["x"], x.astype(">f8"), {}),
        ("y", ["y"], y.astype(">f8"), {}),
        ("time", ["time"], minutes.astype(">f8"), {}),
    ]
    for i, name in enumerate(fields):
        data = np.full((len(hours), 3, 3), 0.1 * (i + 1), ">f4")
        data[:, 0, 0] = -9999.0
        variables.append((name, ["time", "y", "x"], data, {"_FillValue": -9999.0}))
    return nc3_writer.write(
        dims=[("time", None), ("y", 3), ("x", 3)], variables=variables, numrecs=len(hours)
    )


class _Resp:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.status, self._body = status, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self) -> bytes:
        return self._body


class _Session:
    """Answers get_anal_times with ``runs`` and get_matroos windows with a NetCDF.

    ``computed_to`` says how far each run has been computed (by run stamp);
    beyond that Matroos answers with its one-line "no data" text, exactly as it
    does for a run that is still being produced.
    """

    NO_DATA = (
        b"ERROR in matroos.pl: er is geen data beschikbaar voor de gespecificeerde "
        b"bron in de gevraagde periode."
    )

    def __init__(
        self,
        runs: list[str],
        missing_hours: set[int] = frozenset(),
        computed_to: dict[str, int] | None = None,
    ) -> None:
        self.runs, self.missing, self.windows = runs, set(missing_hours), []
        self.computed_to = computed_to or {}

    def get(self, url: str, timeout=None):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        if "get_anal_times" in url:
            return _Resp(("\n".join(self.runs) + "\n").encode())
        start = datetime.strptime(q["from"], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        end = datetime.strptime(q["to"], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        run = datetime.strptime(q["anal"], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        self.windows.append((int((start - run).total_seconds() // 3600), int((end - run).total_seconds() // 3600), q))
        hours = [
            int((start - run).total_seconds() // 3600) + i
            for i in range(int((end - start).total_seconds() // 3600) + 1)
        ]
        last = self.computed_to.get(q["anal"])
        hours = [h for h in hours if h not in self.missing and (last is None or h <= last)]
        if not hours:
            return _Resp(self.NO_DATA)
        return _Resp(_matroos_nc(run, hours, q["color"].split(",")))

    def probes(self) -> list[str]:
        """The run stamps the completeness check asked about (one hour each)."""
        return [q["anal"] for start, end, q in self.windows if start == end]


@pytest.mark.asyncio
async def test_lists_the_newest_six_hourly_run() -> None:
    src = RwsSource(_Session(["202609160900", "202609161200", "202609161500", "garbage"]))
    files = await src.async_list_files(DCSM)
    assert [f.filename for f in files] == ["202609161200"]


@pytest.mark.asyncio
async def test_a_run_that_is_still_being_computed_is_skipped() -> None:
    # The newest six-hourly run stops at +40 h: it is still being produced, so
    # the run before it -- the one we most likely already have -- is used.
    session = _Session(
        ["202609160600", "202609160900", "202609161200"], computed_to={"202609161200": 40}
    )
    files = await RwsSource(session).async_list_files(DCSM)
    assert [f.filename for f in files] == ["202609160600"]
    assert session.probes() == ["202609161200", "202609160600"]


@pytest.mark.asyncio
async def test_a_finished_run_is_only_probed_once() -> None:
    session = _Session(["202609161200"])
    src = RwsSource(session)
    for _ in range(3):
        assert [f.filename for f in await src.async_list_files(DCSM)] == ["202609161200"]
    assert session.probes() == ["202609161200"]


@pytest.mark.asyncio
async def test_no_finished_run_lists_nothing() -> None:
    session = _Session(
        ["202609160600", "202609161200"], computed_to={"202609160600": 10, "202609161200": 10}
    )
    assert await RwsSource(session).async_list_files(DCSM) == []


@pytest.mark.asyncio
async def test_matroos_error_text_is_an_error() -> None:
    class _Err(_Session):
        def get(self, url, timeout=None):
            return _Resp(b"ERROR: Given source is not available in 'maps2d' database.")

    with pytest.raises(GribSourceError):
        await RwsSource(_Err([])).async_list_files(DCSM)


@pytest.mark.asyncio
async def test_downloads_the_horizon_in_windows(tmp_path) -> None:
    session = _Session([])
    src = RwsSource(session)
    paths = await src.async_download_run(DCSM, "202609161200", tmp_path, ["current"], horizon_hours=10)
    assert [p.name for p in paths] == [f"202609161200_{h:03d}.npz" for h in range(11)]
    assert [(a, b) for a, b, _ in session.windows] == [(0, 6), (7, 10)]
    q = session.windows[0][2]
    assert q["source"] == "dcsm7_harmonie_bf_f2w" and q["color"] == "sep,velu,velv"
    assert q["coords"] == "WGS84" and q["dtmin"] == "60" and q["format"] == "nc"
    # Fill values became NaN, and the member decodes as a vector.
    current = next(p for p in DCSM.parameters if p.key == "current")
    vec = grib_decode.decode_vector_components(paths[3], current)
    assert np.isnan(vec.u[0, 0]) and vec.u[1, 1] == pytest.approx(0.2)
    assert vec.valid_time == RUN + timedelta(hours=3)


@pytest.mark.asyncio
async def test_a_run_with_gaps_fails(tmp_path) -> None:
    src = RwsSource(_Session([], missing_hours={5}))
    with pytest.raises(GribSourceError, match="missing 1 of 7"):
        await src.async_download_run(DCSM, "202609161200", tmp_path, ["current"], horizon_hours=6)


@pytest.mark.asyncio
async def test_non_netcdf_answer_fails(tmp_path) -> None:
    class _Err(_Session):
        def get(self, url, timeout=None):
            return _Resp(b"ERROR in matroos.pl: fout in aanroep")

    with pytest.raises(GribSourceError, match="ERROR in matroos"):
        await RwsSource(_Err([])).async_download_run(
            DCSM, "202609161200", tmp_path, ["current"], horizon_hours=2
        )


ZUNO = next(d for d in KNOWN_DATASETS if d.key == "rws_dcsm_zuno")


def test_the_zuno_nest_is_the_same_model_on_a_finer_grid() -> None:
    """Matroos interpolates every request itself, so the nest is worth having
    only if it is asked for more finely than the full domain."""
    full = rws._MODELS["rws_dcsm"]
    nest = rws._MODELS["rws_dcsm_zuno"]
    assert nest.source.startswith(full.source)
    assert nest.step_deg < full.step_deg
    assert nest.fields == full.fields
    assert nest.despike == full.despike  # the same coastal spikes to mask


def test_the_zuno_nest_covers_the_dutch_coast() -> None:
    south, west, north, east = ZUNO.bounds
    # Vlissingen, Den Helder, Terschelling, Borkum, and the Channel's east end.
    for lat, lon in ((51.44, 3.57), (52.96, 4.75), (53.36, 5.22), (53.58, 6.66), (50.95, 1.85)):
        assert south <= lat <= north and west <= lon <= east


def test_the_zuno_nest_offers_the_same_parameters_as_the_full_domain() -> None:
    assert [p.key for p in ZUNO.parameters] == [p.key for p in DCSM.parameters]
