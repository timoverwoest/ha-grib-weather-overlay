"""Where this integration keeps its GRIB working files: outside every backup.

Home Assistant backs up by tarring ``/config`` and, if the user asks, the
``share`` and ``media`` folders. This integration churns a lot of large files --
the GRIB records being decoded and a rendered cache of a gigabyte or two once a
few sources are configured -- and all of it can be fetched again. In a backup it
only did harm:

* a working file removed between the backup's file listing and the tar write
  aborts the *entire* backup with ``FileNotFoundError``;
* the cache made every backup gigabytes heavier for no gain.

Supervisor offers no way to exclude a directory (its only folder filter is for
network mounts), so the lever is location. The root is picked once per entry:

* an explicit ``storage_path`` option, when the user set one -- typed in, or
  picked from the network storage added under Settings > System > Storage, in
  which case it is a ``grib_overlay`` folder on that share (a NAS spares the
  local SSD the writes, and Supervisor leaves network storage out of backups);
* otherwise ``/var/tmp/grib_overlay`` -- real disk inside the Home Assistant
  container, and in none of the folders a backup can include. It is wiped when
  the container is recreated (a core update, say), after which the next poll
  downloads the runs again;
* otherwise the system temp dir (other platforms, and tests).

``/tmp`` itself is a *tmpfs* (RAM) in the Home Assistant OS container, which is
why it is not the default: a rendered cache of that size does not belong in RAM.

Up to 0.25 the cache lived in ``/config/grib_overlay`` and from 0.26 to 0.34 in
``/share/grib_overlay``; the coordinator clears both on upgrade.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from homeassistant.core import HomeAssistant
from homeassistant.helpers.hassio import is_hassio

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# First writable candidate wins.
DEFAULT_BASES: tuple[str, ...] = ("/var/tmp",)

# The default root of 0.26-0.34, cleared on upgrade (see the coordinator).
LEGACY_SHARE_ROOT = Path("/share") / DOMAIN

# Transient downloads (the GRIB records being decoded) live beside the
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


def prepare_root(root: Path) -> bool:
    """Blocking: create ``root`` if needed; whether this integration can write there."""
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        _LOGGER.warning("Cannot use %s for the working files: %s", root, err)
        return False
    return _is_writable_dir(root)


def drop_entry_dirs(entry_directory: Path) -> None:
    """Blocking: remove one entry's cache and scratch, after it moved elsewhere.

    Only the two folders named after the entry -- never the root they are in,
    which may be a share the user keeps other things on.
    """
    shutil.rmtree(entry_directory, ignore_errors=True)
    shutil.rmtree(raw_dir_for(entry_directory), ignore_errors=True)


async def async_network_storages(hass: HomeAssistant) -> dict[str, str]:
    """Network storage that can hold the working files, as {root: label}.

    The shares and media folders added under Settings > System > Storage, each
    with a ``grib_overlay`` folder on it -- not its root, which the user may
    keep other files on. Empty without Supervisor, or when it cannot be asked.
    """
    if not is_hassio(hass):
        return {}
    try:
        # Imported here: the hassio component only exists on a Supervisor
        # install, and only a recent Home Assistant has this client.
        from homeassistant.components.hassio import get_supervisor_client  # noqa: PLC0415

        info = await get_supervisor_client(hass).mounts.info()
    except Exception as err:  # noqa: BLE001 -- an optional convenience; never fail the form over it
        _LOGGER.debug("Could not list the network storage: %s", err)
        return {}
    return {
        str(
            PurePosixPath(mount.user_path) / DOMAIN
        ): f"{mount.name} ({mount.user_path})"
        for mount in info.mounts
        if mount.user_path and mount.usage in ("share", "media") and not mount.read_only
    }


def overlaps(a: Path, b: Path) -> bool:
    """True when one path is the other or lies inside it."""
    a, b = Path(os.path.abspath(a)), Path(os.path.abspath(b))
    return a == b or a in b.parents or b in a.parents
