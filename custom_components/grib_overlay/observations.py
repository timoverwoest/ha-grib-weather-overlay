"""Fetch recent station observations to validate/correct the GRIB forecasts.

Two providers, chosen by the parameter:

- **KNMI EDR** (weather params: wind, gusts, temperature, dewpoint, humidity,
  precipitation, pressure, visibility) — queried by position (nearest station)
  from the 10-minute in-situ observation collection. Uses the KNMI Open Data key
  the integration already stores (any configured ``knmi`` entry's ``api_key``).
- **RWS Waterinfo — WaterWebservices** (water params: wave height/period/
  direction, current) — keyless JSON; the station catalogue is fetched once and
  cached, then the nearest station offering the parameter is queried.

Each provider returns a series ``[{valid_time, value, direction?}]`` in the
parameter's SOURCE unit (the same unit the forecast ``point`` endpoint reports),
so the card can line the observations up with the forecast columns and compute a
delta directly.

NOTE: the provider parameter codes and request shapes here are best-effort from
the public documentation and should be verified against a live key/endpoint. The
response *parsers* are pure and unit-tested with representative fixtures; if a
provider names a field differently, adjust the ``KNMI_EDR`` / ``RWS_AQUO`` maps —
the plumbing around them does not change.
"""

from __future__ import annotations

import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_SOURCE, DOMAIN

_TIMEOUT = 20  # seconds; a slow provider must not hang the card

# --- KNMI EDR (weather) ----------------------------------------------------
# param_key -> (EDR parameter code, unit scale to the forecast source unit).
# The 10-minute in-situ collection uses KNMI's short codes.
KNMI_EDR_BASE = (
    "https://api.dataplatform.knmi.nl/edr/v1/collections/"
    "10-minute-in-situ-meteorological-observations"
)
KNMI_EDR: dict[str, tuple[str, float]] = {
    "wind_10m": ("ff", 1.0),          # 10-min mean wind speed (m/s)
    "wind_gust_10m": ("fx", 1.0),     # max 3-s gust (m/s)
    "temperature_2m": ("ta", 1.0),    # air temperature (degC)
    "dewpoint_2m": ("td", 1.0),       # dew point (degC)
    "humidity_2m": ("rh", 1.0),       # relative humidity (%)
    "precipitation": ("rg", 1.0),     # precipitation sum over the interval (mm)
    "pressure_msl": ("pp", 1.0),      # MSL pressure (hPa)
    "visibility": ("zm", 0.001),      # meteorological range (m) -> km
}
# Companion from-direction code for the vector params (so the Meting row can show
# an arrow, like the manual measurement row does).
KNMI_EDR_DIR: dict[str, str] = {"wind_10m": "dd", "wind_gust_10m": "dd"}

# --- RWS Waterinfo (water) -------------------------------------------------
RWS_BASE = "https://waterwebservices.rijkswaterstaat.nl"
RWS_CATALOGUS = f"{RWS_BASE}/METADATASERVICES_DBO/OphalenCatalogus"
RWS_WAARNEMINGEN = f"{RWS_BASE}/ONLINEWAARNEMINGENSERVICES_DBO/OphalenWaarnemingen"
# param_key -> (AQUO grootheid code, optional companion direction grootheid).
RWS_AQUO: dict[str, tuple[str, str | None]] = {
    "wave_height": ("Hm0", None),          # significant wave height (m)
    "wave_period": ("Tm02", None),         # mean wave period (s)
    "wave_direction": ("Th0", None),       # mean wave direction (deg)
    "current": ("Stroomsnelheid", "Stroomrichting"),  # surface current (m/s, deg)
}
_RWS_MISSING = 999999999.0  # RWS sentinel for a missing value


def provider_for(param_key: str) -> str | None:
    """Which observation provider serves this forecast parameter, if any."""
    if param_key in KNMI_EDR:
        return "knmi"
    if param_key in RWS_AQUO:
        return "rws"
    return None


def _knmi_api_key(hass: HomeAssistant) -> str | None:
    """The Open Data key of any configured KNMI entry (they share one platform)."""
    for coordinator in hass.data.get(DOMAIN, {}).values():
        entry = getattr(coordinator, "entry", None)
        if entry is not None and entry.data.get(CONF_SOURCE) == "knmi":
            key = entry.data.get(CONF_API_KEY)
            if key:
                return key
    return None


async def fetch_observations(
    hass: HomeAssistant, param_key: str, lat: float, lon: float, start: str, end: str
) -> dict[str, Any] | None:
    """Return ``{provider, unit, station, series}`` for a parameter near a point.

    ``start``/``end`` are ISO-8601 UTC strings bounding the window (observations
    only exist up to now, so future columns simply get no value). Returns ``None``
    when no provider serves the parameter, or ``{"error": ...}`` on a fetch/parse
    failure so the card can show a message instead of silently failing.
    """
    provider = provider_for(param_key)
    if provider == "knmi":
        return await _fetch_knmi(hass, param_key, lat, lon, start, end)
    if provider == "rws":
        return await _fetch_rws(hass, param_key, lat, lon, start, end)
    return None


# ---------------------------------------------------------------------------
# KNMI EDR
# ---------------------------------------------------------------------------
async def _fetch_knmi(
    hass: HomeAssistant, param_key: str, lat: float, lon: float, start: str, end: str
) -> dict[str, Any]:
    key = _knmi_api_key(hass)
    if not key:
        return {"error": "no KNMI Open Data key configured"}
    code, scale = KNMI_EDR[param_key]
    dir_code = KNMI_EDR_DIR.get(param_key)
    names = code if not dir_code else f"{code},{dir_code}"
    params = {
        "coords": f"POINT({lon} {lat})",
        "parameter-name": names,
        "datetime": f"{start}/{end}",
        "f": "CoverageJSON",
    }
    url = f"{KNMI_EDR_BASE}/position"
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            url, params=params, headers={"Authorization": key}, timeout=_TIMEOUT
        ) as resp:
            if resp.status != 200:
                return {"error": f"KNMI EDR HTTP {resp.status}"}
            data = await resp.json()
    except Exception as err:  # noqa: BLE001 - surface a clean message to the card
        return {"error": f"KNMI EDR request failed: {err}"}
    series = parse_knmi_coveragejson(data, code, dir_code, scale)
    station = _knmi_station(data, lat, lon)
    return {"provider": "knmi", "unit": None, "station": station, "series": series}


def _knmi_station(data: dict, lat: float, lon: float) -> dict[str, Any]:
    """Best-effort station label/coords from the coverage (falls back to query)."""
    try:
        axes = data["domain"]["axes"]
        sx = float(axes["x"]["values"][0])
        sy = float(axes["y"]["values"][0])
    except (KeyError, IndexError, TypeError, ValueError):
        sx, sy = lon, lat
    name = None
    try:
        # EDR may carry a station id/name under parameters or a properties block.
        name = data.get("properties", {}).get("name")
    except AttributeError:
        name = None
    return {"name": name or "KNMI-station", "lat": sy, "lon": sx, "provider": "knmi"}


def parse_knmi_coveragejson(
    data: dict, value_code: str, dir_code: str | None, scale: float = 1.0
) -> list[dict]:
    """CoverageJSON (PointSeries) -> ``[{valid_time, value, direction?}]``.

    Zips the time axis with the value range (and the optional direction range),
    dropping instants whose value is null. Pure so it can be unit-tested.
    """
    try:
        times = data["domain"]["axes"]["t"]["values"]
        values = data["ranges"][value_code]["values"]
    except (KeyError, TypeError):
        return []
    dirs = None
    if dir_code:
        try:
            dirs = data["ranges"][dir_code]["values"]
        except (KeyError, TypeError):
            dirs = None
    out: list[dict] = []
    for i, t in enumerate(times):
        v = values[i] if i < len(values) else None
        if v is None:
            continue
        point: dict[str, Any] = {"valid_time": t, "value": round(float(v) * scale, 3)}
        if dirs is not None and i < len(dirs) and dirs[i] is not None:
            point["direction"] = round(float(dirs[i]), 0)
        out.append(point)
    return out


# ---------------------------------------------------------------------------
# RWS Waterinfo
# ---------------------------------------------------------------------------
async def _rws_catalogus(hass: HomeAssistant) -> dict | None:
    """The RWS station/parameter catalogue, cached on hass.data for the session."""
    cache = hass.data.setdefault(DOMAIN + "_rws_cat", {})
    if "data" in cache:
        return cache["data"]
    session = async_get_clientsession(hass)
    body = {"CatalogusFilter": {"Grootheden": True, "Locaties": True}}
    try:
        async with session.post(RWS_CATALOGUS, json=body, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except Exception:  # noqa: BLE001
        return None
    cache["data"] = data
    return data


async def _fetch_rws(
    hass: HomeAssistant, param_key: str, lat: float, lon: float, start: str, end: str
) -> dict[str, Any]:
    grootheid, dir_grootheid = RWS_AQUO[param_key]
    cat = await _rws_catalogus(hass)
    if not cat:
        return {"error": "RWS catalogue unavailable"}
    station = nearest_rws_station(cat, grootheid, lat, lon)
    if not station:
        return {"error": "no RWS station with this parameter nearby"}
    session = async_get_clientsession(hass)

    async def _one(gr: str) -> list[dict]:
        body = _rws_waarnemingen_body(station, gr, start, end)
        try:
            async with session.post(RWS_WAARNEMINGEN, json=body, timeout=_TIMEOUT) as resp:
                if resp.status != 200:
                    return []
                return parse_rws_waarnemingen(await resp.json())
        except Exception:  # noqa: BLE001
            return []

    series = await _one(grootheid)
    if dir_grootheid:
        dir_series = await _one(dir_grootheid)
        by_t = {p["valid_time"]: p["value"] for p in dir_series}
        for p in series:
            if p["valid_time"] in by_t:
                p["direction"] = round(by_t[p["valid_time"]], 0)
    return {
        "provider": "rws",
        "unit": None,
        "station": {
            "name": station.get("Naam") or "RWS-station",
            "lat": station.get("_lat"),
            "lon": station.get("_lon"),
            "provider": "rws",
        },
        "series": series,
    }


def _rws_waarnemingen_body(station: dict, grootheid: str, start: str, end: str) -> dict:
    return {
        "Locatie": {
            "Code": station.get("Code"),
            "X": station.get("X"),
            "Y": station.get("Y"),
        },
        "AquoPlusWaarnemingMetadata": {
            "AquoMetadata": {"Grootheid": {"Code": grootheid}}
        },
        "Periode": {"Begindatumtijd": start, "Einddatumtijd": end},
    }


def nearest_rws_station(
    cat: dict, grootheid: str, lat: float, lon: float
) -> dict | None:
    """Nearest catalogue station that offers ``grootheid``, with WGS84 coords added.

    RWS stations carry X/Y in EPSG:25831 (UTM zone 31N); we convert to lat/lon to
    rank by distance and to report the station position back to the card.
    """
    locs = cat.get("LocatieLijst") or []
    # Which location codes offer this grootheid (via the coupling list, when present).
    allowed: set[str] | None = None
    coupling = cat.get("AquoMetadataLocatieLijst")
    meta = cat.get("AquoMetadataLijst")
    if coupling and meta:
        meta_ids = {
            m.get("AquoMetadata_MessageID")
            for m in meta
            if (m.get("Grootheid") or {}).get("Code") == grootheid
        }
        allowed = {
            c.get("Locatie_MessageID")
            for c in coupling
            if c.get("AquoMetaData_MessageID") in meta_ids
            or c.get("AquoMetadata_MessageID") in meta_ids
        }
    best = None
    best_d = float("inf")
    for loc in locs:
        if allowed is not None and loc.get("Locatie_MessageID") not in allowed:
            continue
        try:
            x = float(loc["X"])
            y = float(loc["Y"])
        except (KeyError, TypeError, ValueError):
            continue
        slat, slon = utm31n_to_wgs84(x, y)
        d = _haversine_km(lat, lon, slat, slon)
        if d < best_d:
            best_d = d
            best = {**loc, "_lat": slat, "_lon": slon, "_dist_km": d}
    return best


def parse_rws_waarnemingen(data: dict) -> list[dict]:
    """RWS OphalenWaarnemingen JSON -> ``[{valid_time, value}]`` (pure, testable)."""
    if not data or not data.get("Succesvol", True):
        return []
    out: list[dict] = []
    for w in data.get("WaarnemingenLijst") or []:
        for m in w.get("MetingenLijst") or []:
            t = m.get("Tijdstip")
            mw = m.get("Meetwaarde") or {}
            v = mw.get("Waarde_Numeriek")
            if t is None or v is None:
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if abs(v) >= _RWS_MISSING:
                continue
            out.append({"valid_time": t, "value": round(v, 3)})
    return out


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371.0
    d_lat = math.radians(b_lat - a_lat)
    d_lon = math.radians(b_lon - a_lon)
    s = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(s))


def utm31n_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Inverse UTM (EPSG:25831, zone 31N, WGS84 ellipsoid) -> (lat, lon) in degrees.

    Standard series inversion (Snyder); accurate to well under a metre, which is
    plenty for ranking stations by distance.
    """
    a = 6378137.0
    f = 1 / 298.257223563
    k0 = 0.9996
    e2 = f * (2 - f)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    x = x - 500000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
    )
    ep2 = e2 / (1 - e2)
    c1 = ep2 * math.cos(phi1) ** 2
    t1 = math.tan(phi1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon_rad = (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / math.cos(phi1)
    lon0 = math.radians(3.0)  # zone 31N central meridian = 3°E
    return math.degrees(lat), math.degrees(lon0 + lon_rad)
