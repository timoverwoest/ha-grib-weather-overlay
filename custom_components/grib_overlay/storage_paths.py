"""Where this integration keeps its GRIB working files: outside every backup.

Home Assistant backs up by tarring ``/config`` and, if the user asks, the
``share`` and ``media`` folders. This integration churns a lot of large files --
run archives, extracted members and a rendered cache of a gigabyte or two once a
few sources are configured -- and all of it can be fetched again. In a backup it
only did harm:

* a working file removed between the backup's file listing and the tar write
  aborts the *entire* backup with ``FileNotFoundError``;
* the cache made every backup gigabytes heavier for no gain.

Supervisor offers no way to exclude a directory (its only folder filter is for
network mounts), so the lever is location. The root is picked once per entry:

* an explicit ``storage_path`` option, when the user set one;
* otherwise ``/var/tmp/grib_overlay`` -- real disk inside the Home Assistant
  container, and in none of the folders a backup can include. It is wiped when
  the container is recreated (a core update, say), after which the next poll
  downloads the runs again;
* otherwise the system temp dir (other platforms, and tests).

``/tmp`` itself is a *tmpfs* (RAM) in the Home Assistant OS container, which is
why it is not the default: an 850MB run archive does not belong in RAM.

Up to 0.25 the cache lived in ``/config/grib_overlay`` and from 0.26 to 0.34 in
``/share/grib_overlay``; the coordinator clears both on upgrade.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .const import DOMAIN

# First writable candidate wins.
DEFAULT_BASES: tuple[str, ...] = ("/var/tmp",)

# The default root of 0.26-0.34, cleared on upgrade (see the coordinator).
LEGACY_SHARE_ROOT = Path("/share") / DOMAIN

# Transient downloads (run archives, extracted GRIB members) live beside the
# per-entry directories rather than inside one, so the run-retention cleanup --
# which walks the entry directory -- can never touch an in-flight download.
RAW_DIR_NAME = ".raw"


def _is_writable_dir(path: Path) -> bool:
    """True when ``path`` exists as a directory we may write into.

    Only stat-level calls, so this is safe to call from the event loop.
    """
    return path.is_dir() and os.access(path, os.W_OK)


def default_storage_root(bases: tuple[str, ...] = DEFAULT_BASES) -> Path:
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


def scratch_dir(configured: str | None, entry_id: str) -> Path:
    """Scratch directory for one config entry's in-flight downloads."""
    return raw_dir_for(entry_dir(configured, entry_id))


def raw_dir_for(entry_directory: Path) -> Path:
    """Scratch directory for one entry's in-flight downloads.

    Derived from the entry directory (rather than stored) so relocating
    ``storage_dir`` -- as the tests do -- moves the scratch space with it.
    """
    return entry_directory.parent / RAW_DIR_NAME / entry_directory.name


def overlaps(a: Path, b: Path) -> bool:
    """True when one path is the other or lies inside it."""
    a, b = Path(os.path.abspath(a)), Path(os.path.abspath(b))
    return a == b or a in b.parents or b in a.parents
