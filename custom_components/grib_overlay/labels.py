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
    "wave_direction": "Wave direction (mean)",
    "current": "Sea current (surface)",
}

DATASET_NAMES_EN: dict[str, str] = {
    "harmonie_arome_cy43_p1": "HARMONIE-AROME Cy43 - Netherlands, near-surface parameters",
    "harmonie_arome_cy43_p3": "HARMONIE-AROME Cy43 - Europe (DINI), near-surface parameters",
    "ewam": "DWD EWAM - European waves (North Sea, Atlantic Ocean, Mediterranean)",
    "bsh_current_northsea": "BSH - North Sea currents (NL/BE/FR coast)",
}

SOURCE_NAMES_EN: dict[str, str] = {
    "DWD Open Data (golven)": "DWD Open Data (waves)",
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
