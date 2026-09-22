"""The README documents what the integration actually offers.

Three things drift silently otherwise: a new dataset that never gets described,
a chapter that never reaches the contents list, and a link to a heading that was
since renamed. None of them break anything, which is exactly why nobody notices.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
from pathlib import Path

from custom_components.grib_overlay.sources.registry import SOURCE_REGISTRY

README_PATH = Path("README.md")
README = README_PATH.read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("dev_toc", Path("dev/toc.py"))
toc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(toc)


def _datasets():
    for cls in SOURCE_REGISTRY.values():
        module = importlib.import_module(cls.__module__)
        for dataset in getattr(module, "KNOWN_DATASETS", ()):
            yield cls.key, dataset


def test_every_dataset_is_described_in_both_languages() -> None:
    """Each one gets its own entry under "Bronnen en datasets" / "Sources and
    datasets" -- twice, because the README is bilingual."""
    for source_key, dataset in _datasets():
        assert README.count(f"**`{dataset.key}`**") == 2, f"{source_key}/{dataset.key}"


def test_every_dataset_is_in_the_reference_table() -> None:
    for source_key, dataset in _datasets():
        assert f"| `{dataset.key}` |" in README, f"{source_key}/{dataset.key}"


def test_every_source_is_listed_with_its_key() -> None:
    for key in SOURCE_REGISTRY:
        assert README.count(f"| `{key}` |") >= 2, key


def test_the_contents_lists_are_up_to_date() -> None:
    """Run `python3 dev/toc.py` when this fails."""
    assert toc.rebuild(README) == README


def test_no_link_points_at_a_heading_that_is_not_there() -> None:
    available = toc.anchors(README)
    broken = sorted(
        {a for a in re.findall(r"\]\(#([^)]+)\)", README) if a not in available}
    )
    assert broken == []
