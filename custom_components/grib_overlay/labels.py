"""English display names for the things the config flow lists.

Sources define their datasets and parameters with Dutch names (the project's
first language). Home Assistant's own translation files cannot help here: the
dataset and parameter lists are built at runtime from what the provider offers,
so their labels never pass through ``strings.json``.

The cards translate these names themselves (they know the user's personal
language). A config flow does not have that luxury, so it falls back to the
instance language -- ``hass.config.language``, what the Home Assistant admin set
under Settings -> System -> General.

Dutch needs no table: it is what the sources already carry.
"""

from __future__ import annotations

from typing import Any

DEFAULT_LANGUAGE = "en"

PARAMETER_NAMES_EN: dict[str, str] = {
    "wind_10m": "Wind (10 m)",
    "wind_gust_10m": "Wind gusts (10 m)",
    "temperature_2m": "Temperature (2 m)",
    "dewpoint_2m": "Dew point (2 m)",
    "humidity_2m": "Relative humidity (2 m)",
    "precipitation": "Precipitation",
    "pressure_msl": "Pressure (mean sea level)",
    "visibility": "Visibility",
    "cloud_cover": "Cloud cover",
    "wave_height": "Wave height (significant)",
    "wave_period": "Wave period (mean)",
    # Not "(mean)": EWAM and DMI publish a mean over the spectrum, GFS-Wave the
    # direction of the dominant wave. One key, so the label stays neutral.
    "wave_direction": "Wave direction",
    "wave_peak_period": "Waves: peak period",
    "swell_height": "Swell: height",
    "swell_period": "Swell: period (mean)",
    "swell_peak_period": "Swell: peak period",
    "swell_direction": "Swell: direction",
    "wind_wave_height": "Wind waves: height",
    "wind_wave_period": "Wind waves: period (mean)",
    "wind_wave_peak_period": "Wind waves: peak period",
    "wind_wave_direction": "Wind waves: direction",
    "current": "Sea current (surface)",
    "water_level": "Water level",
    "water_temperature": "Water temperature",
    "cape": "CAPE (thunderstorm energy)",
}

DATASET_NAMES_EN: dict[str, str] = {
    "harmonie_arome_cy43_p1": "HARMONIE-AROME Cy43 - Netherlands, near-surface parameters",
    "harmonie_arome_cy43_p3": "HARMONIE-AROME Cy43 - Europe (DINI), near-surface parameters",
    "ewam": "DWD EWAM - European waves (North Sea, Atlantic Ocean, Mediterranean)",
    "icon_d2": "DWD ICON-D2 - weather model 2.2 km (Germany, Benelux, southern North Sea)",
    "gwam": "DWD GWAM - global waves (Atlantic approaches, to +174 h)",
    "gfs": "NOAA GFS - global model 0.25° (to +384 h)",
    "gfs_wave": "NOAA GFS-Wave - global waves 0.25° (to +384 h)",
    "bsh_current_northsea": "BSH - North Sea currents (NL/BE/FR coast)",
    "dmi_wam_nsb": "DMI WAM - waves North Sea and Baltic (~5 km)",
    "dmi_wam_natlant": "DMI WAM - waves North Atlantic (0.25°)",
    "dmi_dkss_nsbs": "DMI DKSS - currents and water level North Sea and Baltic (~5 km)",
    "rws_dcsm": "RWS DCSM - currents and water level (Norwegian coast to northern Spain)",
    "rws_dcsm_zuno": (
        "RWS DCSM-ZUNO - currents and water level southern North Sea (fine)"
    ),
    "rws_swan_dcsm": "RWS SWAN - waves North Sea",
    "rws_swan_kuststrook": "RWS SWAN - waves Dutch coast (fine)",
    "metno_oslofjord": "MET Norway - Oslofjord: weather, waves and currents",
    "metno_skagerrak": "MET Norway - Skagerrak: weather, waves and currents",
    "metno_sorlandet": "MET Norway - Sørlandet: weather, waves and currents",
}

SOURCE_NAMES_EN: dict[str, str] = {
    "BSH (zeestroming Noordzee)": "BSH (North Sea currents)",
}


def language(hass: Any) -> str:
    """The instance language, normalised to one we ship ("nl" or "en")."""
    raw = ""
    try:
        raw = str(hass.config.language or "")
    except AttributeError:
        pass
    return "nl" if raw.lower().startswith("nl") else DEFAULT_LANGUAGE


def parameter_name(lang: str, parameter: Any) -> str:
    """Display name for a GribParameter in ``lang``."""
    if lang != "nl":
        return PARAMETER_NAMES_EN.get(parameter.key, parameter.name)
    return parameter.name


def dataset_name(lang: str, dataset: Any) -> str:
    """Display name for a GribDatasetInfo in ``lang``."""
    if lang != "nl":
        return DATASET_NAMES_EN.get(dataset.key, dataset.name)
    return dataset.name


def source_name(lang: str, name: str) -> str:
    """Display name for a source class in ``lang``."""
    if lang != "nl":
        return SOURCE_NAMES_EN.get(name, name)
    return name
