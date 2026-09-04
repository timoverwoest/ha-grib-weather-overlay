"""Where the GRIB working files land -- the rule that keeps backups healthy.

Home Assistant tars the whole config folder for a backup, so the one thing these
tests must pin down is that nothing we write resolves inside it, and that the
scratch space for in-flight downloads stays clear of the run directories the
retention cleanup walks.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from custom_components.grib_overlay import storage_paths
from custom_components.grib_overlay.const import DOMAIN


def test_default_root_prefers_a_writable_base(tmp_path: Path) -> None:
    base = tmp_path / "share"
    base.mkdir()
    assert storage_paths.default_storage_root((str(base),)) == base / DOMAIN


def test_default_root_skips_missing_bases_and_falls_back_to_tempdir(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    root = storage_paths.default_storage_root((str(missing),))
    assert root == Path(tempfile.gettempdir()) / DOMAIN


def test_configured_path_wins_and_is_stripped(tmp_path: Path) -> None:
    assert storage_paths.storage_root(f"  {tmp_path}/custom  ") == tmp_path / "custom"
    # Blank/whitespace-only is treated as "not configured".
    assert storage_paths.storage_root("   ") == storage_paths.default_storage_root()
    assert storage_paths.storage_root(None) == storage_paths.default_storage_root()


def test_entry_dir_is_per_entry_under_the_root(tmp_path: Path) -> None:
    entry = storage_paths.entry_dir(str(tmp_path), "01ABC")
    assert entry == tmp_path / "01ABC"


def test_raw_dir_sits_beside_the_entry_dir_not_inside_it(tmp_path: Path) -> None:
    # The retention cleanup deletes stale *subdirectories* of the entry dir, so
    # an in-flight download must never live inside it.
    entry = storage_paths.entry_dir(str(tmp_path), "01ABC")
    raw = storage_paths.raw_dir_for(entry)
    assert raw == tmp_path / storage_paths.RAW_DIR_NAME / "01ABC"
    assert entry not in raw.parents


def test_default_root_is_never_inside_the_config_folder() -> None:
    # The whole point of the module: /config is tarred for every backup.
    assert "/config" not in str(storage_paths.default_storage_root())
