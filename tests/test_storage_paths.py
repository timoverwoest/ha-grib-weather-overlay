"""Where the GRIB working files land -- the rule that keeps backups healthy.

Home Assistant backs up /config and, if asked, /share and /media. The one thing
these tests must pin down is that nothing we write by default resolves inside
any of those, and that in-flight downloads stay clear of the run directories
the retention cleanup walks.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from custom_components.grib_overlay import storage_paths
from custom_components.grib_overlay.const import DOMAIN


def test_default_root_prefers_a_writable_base(tmp_path: Path) -> None:
    base = tmp_path / "var-tmp"
    base.mkdir()
    assert storage_paths.default_storage_root((str(base),)) == base / DOMAIN


def test_default_root_skips_missing_bases_and_falls_back_to_tempdir(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    root = storage_paths.default_storage_root((str(missing),))
    assert root == Path(tempfile.gettempdir()) / DOMAIN


def test_default_root_is_in_no_backup_folder() -> None:
    """The whole point: the cache can be downloaded again, a backup can't lose it."""
    assert storage_paths.DEFAULT_BASES == ("/var/tmp",)
    root = str(storage_paths.default_storage_root())
    for backed_up in ("/config", "/share", "/media"):
        assert not root.startswith(backed_up), f"cache must not live under {backed_up}"


def test_configured_path_wins_and_is_stripped(tmp_path: Path) -> None:
    assert storage_paths.storage_root(f"  {tmp_path}/custom  ") == tmp_path / "custom"
    # Blank/whitespace-only is treated as "not configured".
    assert storage_paths.storage_root("   ") == storage_paths.default_storage_root()
    assert storage_paths.storage_root(None) == storage_paths.default_storage_root()


def test_entry_dir_is_per_entry_under_the_root(tmp_path: Path) -> None:
    assert storage_paths.entry_dir(str(tmp_path), "01ABC") == tmp_path / "01ABC"


def test_scratch_sits_beside_the_entry_dir_not_inside_it(tmp_path: Path) -> None:
    # The retention cleanup deletes stale *subdirectories* of the entry dir, so
    # an in-flight download must never live inside it.
    for configured in (str(tmp_path), None):
        entry = storage_paths.entry_dir(configured, "01ABC")
        scratch = storage_paths.scratch_dir(configured, "01ABC")
        assert scratch == entry.parent / storage_paths.RAW_DIR_NAME / "01ABC"
        assert entry not in scratch.parents and scratch != entry


def test_overlaps() -> None:
    root = Path("/share/grib_overlay")
    assert storage_paths.overlaps(root, root)
    assert storage_paths.overlaps(root, root / "01ABC")
    assert storage_paths.overlaps(root / "01ABC", root)
    assert not storage_paths.overlaps(root, Path("/share/grib_overlay_other"))
    assert not storage_paths.overlaps(root, Path("/var/tmp/grib_overlay"))
