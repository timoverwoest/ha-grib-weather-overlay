"""Backup platform: pause GRIB file churn while Home Assistant makes a backup.

Home Assistant archives the whole ``/config`` folder for a backup. This
integration continuously downloads and deletes GRIB working files under
``/config/grib_overlay/...``; a file removed between the backup's file listing
and the tar write makes the backup fail with ``FileNotFoundError`` (the whole
backup is aborted). Implementing ``async_pre_backup`` / ``async_post_backup``
lets us pause that churn for the duration of the backup -- the same mechanism the
recorder uses to keep its database consistent.

Requires Home Assistant to invoke backup platform hooks (its 2025.1+ backup
system does this for both core and Home Assistant OS backups). On older cores the
hooks are simply never called and this is a no-op; the coordinator's relocation
of raw per-file downloads to ``/tmp`` still keeps those out of the backup there.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import GribOverlayCoordinator

_LOGGER = logging.getLogger(__name__)

# Cap how long we wait for an in-flight run to finish before letting the backup
# proceed, so a long download can never stall the backup indefinitely.
_DRAIN_TIMEOUT = 60


async def async_pre_backup(hass: HomeAssistant) -> None:
    """Pause run processing (and thus file deletion) before a backup starts."""
    GribOverlayCoordinator.set_backup_active(True)
    for coordinator in list(hass.data.get(DOMAIN, {}).values()):
        try:
            await asyncio.wait_for(
                _drain(coordinator._process_lock), timeout=_DRAIN_TIMEOUT
            )
        except Exception as err:  # noqa: BLE001 - must never abort the backup
            _LOGGER.debug("Pre-backup drain skipped for a coordinator: %s", err)


async def async_post_backup(hass: HomeAssistant) -> None:
    """Resume normal processing once the backup has finished."""
    GribOverlayCoordinator.set_backup_active(False)


async def _drain(lock: asyncio.Lock) -> None:
    """Return once no run is currently being processed under ``lock``."""
    async with lock:
        return
