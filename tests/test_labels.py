"""Dataset/parameter labels follow the instance language in the config flow.

Home Assistant's own translation files can't reach these: the lists are built at
runtime from what the provider offers, so their names never pass through
strings.json. Dutch is whatever the source itself carries; English comes from a
table, and an unknown key has to fall through to the source's own name rather
than disappear.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from custom_components.grib_overlay import labels


def _hass(language: str | None):
    return SimpleNamespace(config=SimpleNamespace(language=language))


def test_language_normalises_to_a_shipped_language() -> None:
    assert labels.language(_hass("nl")) == "nl"
    assert labels.language(_hass("nl-NL")) == "nl"
    assert labels.language(_hass("en")) == "en"
    # Anything we don't ship falls back to English, not to Dutch.
    assert labels.language(_hass("de")) == "en"
    assert labels.language(_hass(None)) == "en"
    assert labels.language(SimpleNamespace()) == "en"


def test_parameter_names_translate_and_fall_back() -> None:
    wind = SimpleNamespace(key="wind_10m", name="Wind (10m)")
    assert labels.parameter_name("nl", wind) == "Wind (10m)"
    assert labels.parameter_name("en", wind) == "Wind (10 m)"

    unknown = SimpleNamespace(key="soil_moisture", name="Bodemvocht")
    assert labels.parameter_name("en", unknown) == "Bodemvocht"


def test_dataset_names_translate_and_fall_back() -> None:
    ds = SimpleNamespace(
        key="harmonie_arome_cy43_p1",
        name="HARMONIE-AROME Cy43 - Nederland, near-surface parameters",
    )
    assert labels.dataset_name("nl", ds) == ds.name
    assert "Netherlands" in labels.dataset_name("en", ds)

    unknown = SimpleNamespace(key="something_new", name="Iets nieuws")
    assert labels.dataset_name("en", unknown) == "Iets nieuws"


def test_source_names_translate_and_fall_back() -> None:
    assert labels.source_name("nl", "DWD Open Data (golven)") == "DWD Open Data (golven)"
    assert labels.source_name("en", "DWD Open Data (golven)") == "DWD Open Data (waves)"
    # KNMI's name is language-neutral and must be left alone.
    assert labels.source_name("en", "KNMI Data Platform") == "KNMI Data Platform"


def test_every_english_name_covers_a_real_key() -> None:
    """A typo'd key would silently never be used -- catch it here."""
    from custom_components.grib_overlay.sources import bsh, dwd, knmi

    datasets = [*knmi.KNOWN_DATASETS, *dwd.KNOWN_DATASETS, *bsh.KNOWN_DATASETS]
    assert set(labels.DATASET_NAMES_EN) == {d.key for d in datasets}
    assert set(labels.PARAMETER_NAMES_EN) == {p.key for d in datasets for p in d.parameters}


def test_cards_and_config_flow_agree_on_the_english_names() -> None:
    """The card ships its own copy (it knows the user's personal language).

    They are two tables for two different scopes, but they must not drift: a
    parameter has to read the same in the config flow and on the card.
    """
    js = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(encoding="utf-8")

    def js_block(name: str, lang: str) -> dict[str, str]:
        body = js.split(f"const {name} = {{", 1)[1]
        block = body.split(f"  {lang}: {{", 1)[1].split("\n  },", 1)[0]
        return dict(re.findall(r'(\w+):\s*"([^"]+)"', block))

    assert js_block("GRIB_PARAM_NAMES", "en") == labels.PARAMETER_NAMES_EN
    assert js_block("GRIB_DATASET_NAMES", "en") == labels.DATASET_NAMES_EN
    # Dutch is spelled out in the card (it renders without asking the backend),
    # so both languages must offer exactly the same parameters.
    assert set(js_block("GRIB_PARAM_NAMES", "nl")) == set(labels.PARAMETER_NAMES_EN)


def test_card_ships_every_string_in_both_languages() -> None:
    """A key present in one language and not the other renders as English (or
    as the raw key). Cheap to prevent, hard to spot by eye."""
    js = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(encoding="utf-8")
    body = js.split("const GRIB_TEXT = {", 1)[1]
    nl_block = body.split("  nl: {", 1)[1].split("\n  },", 1)[0]
    en_block = body.split("  en: {", 1)[1].split("\n  },", 1)[0]
    keys = lambda block: set(re.findall(r"^    (\w+):", block, re.M))
    missing_en = keys(nl_block) - keys(en_block)
    missing_nl = keys(en_block) - keys(nl_block)
    assert not missing_en, f"missing English strings: {sorted(missing_en)}"
    assert not missing_nl, f"missing Dutch strings: {sorted(missing_nl)}"
    assert len(keys(nl_block)) > 50  # the tables are actually populated
