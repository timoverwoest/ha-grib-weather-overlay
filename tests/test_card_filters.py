"""Which datasets and parameters a card shows (`datasets` / `parameters`).

A card is told in YAML which sources and which parameters it may show, so wave
data can be kept off the weather card and given a card of its own. Both cards
build everything (dropdowns, meteogram, model comparison) from one entry list,
filtered in a single place; the moment a card fills that list itself again, the
config keys silently stop working. There are no JS tests, so this guards the
lines that matter -- and the README that documents the keys.
"""

from __future__ import annotations

from pathlib import Path

JS = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(encoding="utf-8")
README = Path("README.md").read_text(encoding="utf-8")
FILTERS = JS.split("// --- which datasets and parameters a card shows", 1)[1].split(
    "// Canonical column resolution", 1
)[0]


def _body(name: str) -> str:
    return FILTERS.split(f"function {name}(", 1)[1].split("\n}\n", 1)[0]


def test_both_cards_take_their_entries_from_the_filter() -> None:
    # Every assignment of an entry list goes through filterCardEntries: the raw
    # response only ever lands in _allEntries (kept for live config edits).
    assert JS.count("this._entries = filterCardEntries(") == JS.count("this._entries =") == 3
    assert JS.count("this._allEntries = data.entries || [];") == 2


def test_the_config_keys_are_the_documented_ones() -> None:
    entries = _body("filterCardEntries")
    assert "cfg.datasets ?? cfg.entries ?? cfg.models" in entries  # `entries`/`models`: compare card
    assert "cfg.exclude_datasets ?? cfg.exclude_entries" in entries
    assert "expandParamTokens(filterTokens(cfg.parameters))" in entries
    assert "expandParamTokens(filterTokens(cfg.exclude_parameters))" in entries
    for key in ("datasets", "exclude_datasets", "parameters", "exclude_parameters"):
        assert README.count(f"`{key}`") >= 2, key  # Dutch and English reference


def test_a_group_name_stands_for_its_parameter_keys() -> None:
    assert '"wave_*", "swell_*", "wind_wave_*"' in FILTERS
    assert 'golven: "waves"' in FILTERS
    # Group names must not collide with real parameter keys, or a list naming
    # one parameter would quietly pull in a whole family.
    keys = {"current", "water_level", "water_temperature", "wave_height", "precipitation"}
    groups = FILTERS.split("const GRIB_PARAM_GROUPS = {", 1)[1].split("};", 1)[0]
    names = {line.split(":", 1)[0].strip() for line in groups.splitlines() if ":" in line}
    assert not (names & keys)


def test_a_kept_wave_parameter_keeps_its_direction() -> None:
    # Filtering on heights alone must not strip the directions the arrows and
    # the from-direction rows are drawn from.
    body = _body("filterCardParameters")
    assert "gribDirectionKeyFor(key)" in body
    assert "!matchesAny(exclude, dir)" in body


def test_an_empty_result_is_explained_on_the_card() -> None:
    assert 'this._els.note.textContent = gribT("noDatasetsMatch");' in JS
    assert JS.count("noDatasetsMatch:") == 2  # Dutch and English
