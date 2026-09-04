"""Where this integration keeps its GRIB working files -- deliberately NOT /config.

Home Assistant backs up by tarring the whole ``/config`` folder. This integration
churns a lot of large files (a HARMONIE run archive is ~850MB and every poll
writes a new run directory and removes the previous one), which broke backups in
two ways:

* a working file removed between the backup's file listing and the tar write
  aborts the *entire* backup with ``FileNotFoundError``;
* the rendered cache (~600MB in practice) bloated every backup for no gain --
  it is a cache, regenerated within minutes of a restart.

So nothing this integration writes lives under ``/config`` any more. The root is
picked once per entry:

* an explicit ``storage_path`` option, when the user set one;
* otherwise ``/share/grib_overlay`` -- present and writable on Home Assistant
  OS/Supervised, on real disk, and outside the config folder that gets tarred;
* otherwise the system temp dir (Core/Container installs, and tests).

Note ``/tmp`` is a *tmpfs* (RAM) inside the Home Assistant OS container, which is
why it is the last resort rather than the default: an 850MB run archive does not
belong in RAM.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .const import DOMAIN

# First writable candidate wins. /share is a real, persistent, read-write mount
# on Home Assistant OS/Supervised and is not part of the config folder backup.
PREFERRED_BASES: tuple[str, ...] = ("/share",)

# Transient downloads (run archives, extracted GRIB members) live beside the
# per-entry directories rather than inside one, so the run-retention cleanup --
# which walks the entry directory -- can never touch an in-flight download.
RAW_DIR_NAME = ".raw"


def _is_writable_dir(path: Path) -> bool:
    """True when ``path`` exists as a directory we may write into.

    Only stat-level calls, so this is safe to call from the event loop.
    """
    return path.is_dir() and os.access(path, os.W_OK)


def default_storage_root(bases: tuple[str, ...] = PREFERRED_BASES) -> Path:
    """The root directory used when the user configured no explicit path."""
    for base in bases:
        candidate = Path(base)
        if _is_writable_dir(candidate):
            return candidate / DOMAIN
    return Path(tempfile.gettempdir()) / DOMAIN


def storage_root(configured: str | None = None) -> Path:
    """Resolve the root holding one working directory per config entry."""
    if configured and configured.strip():
        return Path(configured.strip()).expanduser()
    return default_storage_root()


def entry_dir(configured: str | None, entry_id: str) -> Path:
    """Working directory for one config entry (holds its run directories)."""
    return storage_root(configured) / entry_id


def raw_dir_for(entry_directory: Path) -> Path:
    """Scratch directory for one entry's in-flight downloads.

    Derived from the entry directory (rather than stored) so relocating
    ``storage_dir`` -- as the tests do -- moves the scratch space with it.
    """
    return entry_directory.parent / RAW_DIR_NAME / entry_directory.name
