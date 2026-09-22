"""NOAA GRIB source: the GFS weather model and the GFS-Wave wave model.

GFS is the long-range half of this integration: where HARMONIE, ICON-D2 and
EWAM stop after two or three days, GFS runs to +384 hours. That reach is the
whole point of having it next to the high-resolution models, not a replacement
for them -- at 0.25 degrees it is far coarser over the coast.

Everything is fetched through NCEP's NOMADS *filter* service rather than from
the raw files, and that is not an optimisation but a requirement: the files on
NCEP's own servers use GRIB2 complex packing with spatial differencing
(template 5.3), which the in-tree decoder does not read. The filter service
re-packs whatever you select with simple packing (template 5.0), which it does.

It also cuts a lat/lon window out of the global grid server-side, so one lead
time of the entire parameter set over the window below is tens of kilobytes
instead of hundreds of megabytes. One request per lead time asks for every
enabled parameter at once, which keeps the load on a free public service to one
hit per lead time.

NOMADS keeps roughly the last ten days; no key, no account.
"""

from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp

from .base import (
    GribDatasetInfo,
    GribFileInfo,
    GribParameter,
    GribSource,
    GribSourceError,
)

_CGI = "https://nomads.ncep.noaa.gov/cgi-bin"

# The window cut out of the global grid, (south, west, north, east). Wide enough
# for the approaches a North Sea boat plans around -- Biscay, the Western
# Approaches, Ireland, Iceland, the Norwegian Sea and the Baltic -- while
# keeping a lead time small. Leaving it global would also defeat the point: the
# wind and field endpoints thin a grid to a fixed number of points per axis, so
# a world grid would arrive over the North Sea far coarser than the model is.
WINDOW = (40.0, -25.0, 65.0, 15.0)

# GFS publishes hourly to +120 h and three-hourly from there to +384 h.
_HOURLY_TO = 120
_LAST_STEP = 384

# Runs start at 00/06/12/18 UTC. The first lead times appear about 3 h 20 min
# after the run time; how far back to keep looking for a run that has the lead
# times we need.
_RUN_INTERVAL_HOURS = 6
_RUN_LOOKBACK_HOURS = 24

# Which lead time async_list_files probes to call a run usable. A run is
# announced once it holds the default forecast horizon; async_download_run is
# strict about whatever horizon is actually configured, so a longer horizon on a
# run that is still publishing simply fails and is retried at the next poll.
_PROBE_STEP = 24

# Parallel downloads per run. NOMADS is a free public service with rate limits,
# so this stays well below what the DWD mirror gets.
_DOWNLOAD_CONCURRENCY = 2

_TIMEOUT = aiohttp.ClientTimeout(total=180)

# GRIB2 fixed-surface types used below.
_GROUND = 1  # ground or water surface
_ATMOSPHERE = 10  # entire atmosphere
_SEA_LEVEL = 101
_HEIGHT = 103  # specified height above ground
_SEQUENCE = 241  # ordered sequence of data -- GFS-Wave's swell partitions


def _met(category: int, number: int, level_type: int, level: float) -> dict:
    """GRIB2 filter for an instantaneous meteorological (discipline 0) field.

    The level and the template matter here in a way they do not for the other
    sources: a NOMADS response holds every selected parameter for one lead time
    in one file. A bare category/number would match the same quantity at
    another level (2 m temperature and 2 mb temperature are both discipline 0,
    category 0, number 0), and GFS publishes the precipitation rate and the
    cloud cover twice -- once as the value now, once averaged over the interval
    since the run started.
    """
    return {
        "discipline": 0,
        "parameterCategory": category,
        "parameterNumber": number,
        "indicatorOfTypeOfLevel": level_type,
        "level": level,
        "productDefinitionTemplateNumber": 0,
    }


def _wave(number: int, level_type: int = _GROUND, level: float = 1.0) -> dict:
    """GRIB2 filter for a wave field (discipline 10, category 0)."""
    return {
        "discipline": 10,
        "parameterCategory": 0,
        "parameterNumber": number,
        "indicatorOfTypeOfLevel": level_type,
        "level": level,
    }


@dataclass(frozen=True)
class _Field:
    """One parameter, plus what to ask NOMADS for to get it."""

    parameter: GribParameter
    variables: tuple[str, ...]  # NOMADS var_ names
    levels: tuple[str, ...] = ()  # NOMADS lev_ names; empty means all_lev=on


# The keys deliberately match HARMONIE's, ICON-D2's and EWAM's, so the
# comparison view lines the models up parameter by parameter.
_GFS_FIELDS: tuple[_Field, ...] = (
    _Field(
        GribParameter(
            key="wind_10m",
            name="Wind (10m)",
            unit="m/s",
            kind="vector",
            grib_filter_u=_met(2, 2, _HEIGHT, 10.0),
            grib_filter_v=_met(2, 3, _HEIGHT, 10.0),
            colormap="wind",
            value_range=(0, 25),
        ),
        ("UGRD", "VGRD"),
        ("10_m_above_ground",),
    ),
    _Field(
        GribParameter(
            key="wind_gust_10m",
            name="Windstoten (10m)",
            unit="m/s",
            grib_filter=_met(2, 22, _GROUND, 0.0),
            colormap="wind",
            value_range=(0, 35),
        ),
        ("GUST",),
        ("surface",),
    ),
    _Field(
        GribParameter(
            key="temperature_2m",
            name="Temperatuur (2m)",
            unit="°C",
            grib_filter=_met(0, 0, _HEIGHT, 2.0),
            offset=-273.15,  # Kelvin -> Celsius
            colormap="temperature",
            value_range=(-10, 35),
        ),
        ("TMP",),
        ("2_m_above_ground",),
    ),
    _Field(
        GribParameter(
            key="dewpoint_2m",
            name="Dauwpunt (2m)",
            unit="°C",
            grib_filter=_met(0, 6, _HEIGHT, 2.0),
            offset=-273.15,
            colormap="temperature",
            value_range=(-15, 25),
        ),
        ("DPT",),
        ("2_m_above_ground",),
    ),
    _Field(
        GribParameter(
            key="humidity_2m",
            name="Relatieve luchtvochtigheid (2m)",
            unit="%",
            grib_filter=_met(1, 1, _HEIGHT, 2.0),
            colormap="humidity",
            value_range=(0, 100),
        ),
        ("RH",),
        ("2_m_above_ground",),
    ),
    # The rate, not a total: GFS restarts its precipitation accumulation every
    # six hours, so subtracting consecutive totals (what ``accumulated`` does)
    # would lose the hour that straddles each restart. PRATE is instantaneous.
    _Field(
        GribParameter(
            key="precipitation",
            name="Neerslag",
            unit="mm/u",
            grib_filter=_met(1, 7, _GROUND, 0.0),
            scale=3600.0,  # kg m-2 s-1 -> mm per hour
            colormap="precipitation",
            value_range=(0, 20),
        ),
        ("PRATE",),
        ("surface",),
    ),
    _Field(
        GribParameter(
            key="pressure_msl",
            name="Luchtdruk (zeeniveau)",
            unit="hPa",
            grib_filter=_met(3, 1, _SEA_LEVEL, 0.0),
            scale=0.01,  # Pa -> hPa
            colormap="pressure",
            value_range=(980, 1040),
        ),
        ("PRMSL",),
        ("mean_sea_level",),
    ),
    _Field(
        GribParameter(
            key="visibility",
            name="Zicht",
            unit="km",
            grib_filter=_met(19, 0, _GROUND, 0.0),
            scale=0.001,  # m -> km
            colormap="visibility",
            value_range=(0, 50),
        ),
        ("VIS",),
        ("surface",),
    ),
    _Field(
        GribParameter(
            key="cloud_cover",
            name="Bewolking",
            unit="%",
            grib_filter=_met(6, 1, _ATMOSPHERE, 0.0),
            colormap="cloud",
            value_range=(0, 100),
        ),
        ("TCDC",),
        ("entire_atmosphere",),
    ),
    _Field(
        GribParameter(
            key="cape",
            name="CAPE (onweersenergie)",
            unit="J/kg",
            grib_filter=_met(7, 6, _GROUND, 0.0),
            colormap="cape",
            value_range=(0, 2000),
        ),
        ("CAPE",),
        ("surface",),
    ),
)

# GFS-Wave (WAVEWATCH III). It publishes the period and direction of the
# dominant spectral peak, where EWAM publishes a mean over the whole spectrum;
# the period therefore uses the peak-period key (DMI's WAM does the same), and
# the direction the shared one, since there is only ever one wave direction to
# draw the arrows from.
_GFS_WAVE_FIELDS: tuple[_Field, ...] = (
    _Field(
        GribParameter(
            key="wave_height",
            name="Golfhoogte (significant)",
            unit="m",
            grib_filter=_wave(3),
            colormap="wave",
            value_range=(0, 8),
        ),
        ("HTSGW",),
    ),
    _Field(
        GribParameter(
            key="wave_peak_period",
            name="Golf: piekperiode",
            unit="s",
            grib_filter=_wave(11),
            colormap="wave_period",
            value_range=(0, 16),
        ),
        ("PERPW",),
    ),
    _Field(
        GribParameter(
            key="wave_direction",
            name="Golfrichting (primaire golf)",
            unit="°",
            grib_filter=_wave(10),
            colormap="direction",
            value_range=(0, 360),
        ),
        ("DIRPW",),
    ),
    # Swell arrives split into partitions, ordered by energy; the first one is
    # the dominant swell train and the only one offered here.
    _Field(
        GribParameter(
            key="swell_height",
            name="Deining: hoogte",
            unit="m",
            grib_filter=_wave(8, _SEQUENCE, 1.0),
            colormap="wave",
            value_range=(0, 8),
        ),
        ("SWELL",),
    ),
    _Field(
        GribParameter(
            key="swell_period",
            name="Deining: periode (gemiddeld)",
            unit="s",
            grib_filter=_wave(9, _SEQUENCE, 1.0),
            colormap="wave_period",
            value_range=(0, 16),
        ),
        ("SWPER",),
    ),
    _Field(
        GribParameter(
            key="swell_direction",
            name="Deining: richting",
            unit="°",
            grib_filter=_wave(7, _SEQUENCE, 1.0),
            colormap="direction",
            value_range=(0, 360),
        ),
        ("SWDIR",),
    ),
    _Field(
        GribParameter(
            key="wind_wave_height",
            name="Windgolven: hoogte",
            unit="m",
            grib_filter=_wave(5),
            colormap="wave",
            value_range=(0, 8),
        ),
        ("WVHGT",),
    ),
    _Field(
        GribParameter(
            key="wind_wave_period",
            name="Windgolven: periode (gemiddeld)",
            unit="s",
            grib_filter=_wave(6),
            colormap="wave_period",
            value_range=(0, 16),
        ),
        ("WVPER",),
    ),
    _Field(
        GribParameter(
            key="wind_wave_direction",
            name="Windgolven: richting",
            unit="°",
            grib_filter=_wave(4),
            colormap="direction",
            value_range=(0, 360),
        ),
        ("WVDIR",),
    ),
    # The wind the wave model was driven with, so the sea state and the wind
    # over it come from the same file.
    _Field(
        GribParameter(
            key="wind_10m",
            name="Wind (10m)",
            unit="m/s",
            kind="vector",
            grib_filter_u=_met(2, 2, _GROUND, 1.0),
            grib_filter_v=_met(2, 3, _GROUND, 1.0),
            colormap="wind",
            value_range=(0, 25),
        ),
        ("UGRD", "VGRD"),
    ),
)


@dataclass(frozen=True)
class _Model:
    """One NOMADS filter endpoint and the file names behind it."""

    cgi: str  # filter script name
    directory: str  # path under the run directory
    filename: str  # format string taking run hour and step
    fields: tuple[_Field, ...]

    def field(self, key: str) -> _Field | None:
        return next((f for f in self.fields if f.parameter.key == key), None)


_MODELS = {
    "gfs": _Model(
        cgi="filter_gfs_0p25_1hr.pl",
        directory="atmos",
        filename="gfs.t{hh}z.pgrb2.0p25.f{step:03d}",
        fields=_GFS_FIELDS,
    ),
    "gfs_wave": _Model(
        cgi="filter_gfswave.pl",
        directory="wave/gridded",
        filename="gfswave.t{hh}z.global.0p25.f{step:03d}.grib2",
        fields=_GFS_WAVE_FIELDS,
    ),
}


KNOWN_DATASETS: tuple[GribDatasetInfo, ...] = (
    GribDatasetInfo(
        key="gfs",
        name="NOAA GFS - wereldmodel 0,25° (tot +384 uur)",
        version="1.0",
        description=(
            "NOAA GFS: elk uur een voorspelling tot +120 uur en daarna elke 3 uur "
            "tot +384 uur, vier runs per dag. Grof (~25 km) vergeleken met "
            "HARMONIE of ICON-D2, maar het enige model hier dat verder dan een "
            "paar dagen kijkt. Het gebied is vast: Biskaje en Ierland tot "
            "IJsland, Noorwegen en de Oostzee. Via NOMADS, geen sleutel nodig."
        ),
        grid_type="regular_latlon",
        bounds=WINDOW,
        output_frequency_hours=1,
        forecast_horizon_hours=_LAST_STEP,
        parameters=tuple(f.parameter for f in _GFS_FIELDS),
    ),
    GribDatasetInfo(
        key="gfs_wave",
        name="NOAA GFS-Wave - wereldwijde golven 0,25° (tot +384 uur)",
        version="1.0",
        description=(
            "NOAA GFS-Wave (WAVEWATCH III), aangedreven door GFS: golfhoogte, "
            "deining en windgolven tot +384 uur, vier runs per dag. Zelfde "
            "gebied en zelfde bereik als GFS zelf. Via NOMADS, geen sleutel nodig."
        ),
        grid_type="regular_latlon",
        bounds=WINDOW,
        output_frequency_hours=1,
        forecast_horizon_hours=_LAST_STEP,
        parameters=tuple(f.parameter for f in _GFS_WAVE_FIELDS),
    ),
)


def steps_within(horizon_hours: float) -> list[int]:
    """The lead times GFS publishes up to ``horizon_hours``, ascending."""
    hourly = range(0, min(int(horizon_hours), _HOURLY_TO) + 1)
    three_hourly = range(_HOURLY_TO + 3, _LAST_STEP + 1, 3)
    return [*hourly, *(s for s in three_hourly if s <= horizon_hours)]


def _floor_run(moment: datetime) -> datetime:
    """``moment`` rounded back to the run before it (00/06/12/18 UTC)."""
    return moment.replace(
        hour=moment.hour - moment.hour % _RUN_INTERVAL_HOURS,
        minute=0,
        second=0,
        microsecond=0,
    )


@functools.lru_cache(maxsize=None)
def _window_query() -> str:
    south, west, north, east = WINDOW
    return (
        f"subregion=&leftlon={west}&rightlon={east}&toplat={north}&bottomlat={south}"
    )


class NoaaSource(GribSource):
    """GribSource for NOAA GFS and GFS-Wave through NCEP's NOMADS filter service."""

    key = "noaa"
    name = "NOAA GFS (NOMADS)"
    supports_push_notifications = False
    provides_archive = False

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None,
                 notification_api_key: str | None = None, instance_id: str | None = None) -> None:
        self._session = session  # api_key/instance_id unused: NOMADS needs no key

    async def async_list_datasets(self) -> list[GribDatasetInfo]:
        return list(KNOWN_DATASETS)

    # -- URLs -------------------------------------------------------------------

    def _url(
        self,
        model: _Model,
        run: datetime,
        step: int,
        fields: list[_Field],
        window: str | None = None,
    ) -> str:
        hh = f"{run.hour:02d}"
        variables = sorted({v for f in fields for v in f.variables})
        levels = sorted({lev for f in fields for lev in f.levels})
        # A field with no level of its own (the wave model's, whose swell
        # partitions each sit at their own level) needs the lot.
        selection = "&".join(f"lev_{lev}=on" for lev in levels) if levels else "all_lev=on"
        directory = f"/gfs.{run:%Y%m%d}/{hh}/{model.directory}".replace("/", "%2F")
        return (
            f"{_CGI}/{model.cgi}"
            f"?file={model.filename.format(hh=hh, step=step)}"
            f"&{'&'.join(f'var_{v}=on' for v in variables)}"
            f"&{selection}"
            f"&{window or _window_query()}"
            f"&dir={directory}"
        )

    async def _get(self, url: str) -> bytes | None:
        """The response body, or None when NOMADS does not have that file (yet).

        404 is a lead time that has not been published; 403 is a run time the
        service considers to be in the future. Neither is an error worth
        raising -- both simply mean "look at an older run".
        """
        try:
            async with self._session.get(url, timeout=_TIMEOUT) as resp:
                if resp.status in (403, 404):
                    return None
                if resp.status >= 400:
                    raise GribSourceError(f"NOMADS {url} returned HTTP {resp.status}")
                body = await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GribSourceError(f"NOMADS request failed: {err}") from err
        if not body.startswith(b"GRIB"):
            # The filter answers an unusable selection with an HTML error page.
            return None
        return body

    # -- GribSource -------------------------------------------------------------

    async def async_list_files(
        self,
        dataset: GribDatasetInfo,
        *,
        max_keys: int = 20,
        order_by: str = "lastModified",
        sorting: str = "desc",
    ) -> list[GribFileInfo]:
        """The newest run that has reached _PROBE_STEP, newest first.

        Probed with a single grid cell, which is a couple of hundred bytes --
        cheap enough to ask NOMADS at every poll.
        """
        model = _MODELS[dataset.key]
        field = model.fields[0]
        one_cell = "subregion=&leftlon=4&rightlon=4.25&toplat=53&bottomlat=52.75"
        now = datetime.now(timezone.utc)
        for back in range(0, _RUN_LOOKBACK_HOURS + 1, _RUN_INTERVAL_HOURS):
            run = _floor_run(now - timedelta(hours=back))
            url = self._url(model, run, _PROBE_STEP, [field], window=one_cell)
            if await self._get(url) is not None:
                return [
                    GribFileInfo(
                        filename=f"{run:%Y%m%d%H}", size=0, last_modified=run.isoformat()
                    )
                ]
        return []

    async def async_download_file(
        self, dataset: GribDatasetInfo, filename: str, destination: Path
    ) -> Path:
        raise GribSourceError("NOMADS delivers per lead time; use async_download_run")

    async def async_download_run(
        self,
        dataset: GribDatasetInfo,
        run_id: str,
        run_dir: Path,
        param_keys: list[str],
        horizon_hours: float,
    ) -> list[Path]:
        """One file per lead time, each holding every enabled parameter.

        That is one NOMADS hit per lead time rather than one per parameter, and
        the coordinator already knows how to read a member that holds several
        parameters (it is how KNMI's archives arrive).
        """
        model = _MODELS[dataset.key]
        fields = [f for key in param_keys if (f := model.field(key))]
        if not fields:
            raise GribSourceError(f"No GFS parameters enabled for {dataset.key}")
        run = datetime.strptime(run_id, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, functools.partial(run_dir.mkdir, parents=True, exist_ok=True)
        )

        semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)

        async def fetch(step: int) -> Path:
            async with semaphore:
                body = await self._get(self._url(model, run, step, fields))
            if body is None:
                # The run was complete enough when it was listed but is not for
                # this horizon. Failing here keeps the run out of the cache with
                # gaps in it; the next poll picks it up once it is finished.
                raise GribSourceError(
                    f"GFS run {run_id} is not complete yet: +{step} h is not published"
                )
            dest = run_dir / f"{dataset.key}_{step:03d}.grib2"
            await loop.run_in_executor(None, dest.write_bytes, body)
            return dest

        results = await asyncio.gather(
            *(fetch(step) for step in steps_within(horizon_hours)), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return list(results)
