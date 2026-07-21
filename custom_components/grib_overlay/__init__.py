"""The GRIB Weather Overlay integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .coordinator import GribOverlayCoordinator
from .http import VIEWS

_LOGGER = logging.getLogger(__name__)

FRONTEND_JS_FILENAME = "grib-overlay-card.js"
STATIC_URL_PREFIX = "/grib_overlay_static"
FRONTEND_URL_PATH = f"{STATIC_URL_PREFIX}/{FRONTEND_JS_FILENAME}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one grib_overlay config entry."""
    first_entry = DOMAIN not in hass.data
    hass.data.setdefault(DOMAIN, {})

    coordinator = GribOverlayCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    if first_entry:
        for view in VIEWS:
            hass.http.register_view(view())
        await _async_register_frontend(hass)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one grib_overlay config entry."""
    coordinator: GribOverlayCoordinator | None = hass.data[DOMAIN].pop(entry.entry_id, None)
    if coordinator is not None:
        await coordinator.source.async_stop_notifications()
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the card + vendored Leaflet assets and register the card as a Lovelace resource."""
    www_dir = Path(__file__).parent / "www"
    js_path = www_dir / FRONTEND_JS_FILENAME
    if not js_path.exists():
        _LOGGER.warning("Frontend card not found at %s, skipping registration", js_path)
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_PREFIX, str(www_dir), cache_headers=False)]
    )
    # Append the integration version as a cache-buster: the card is served from
    # a stable path, so without a changing query string browsers (and the HA
    # service worker) keep serving the previously cached card after an update.
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = integration.version or "0"
    except Exception:  # noqa: BLE001 - fall back to an unversioned URL if lookup fails
        version = "0"
    add_extra_js_url(hass, f"{FRONTEND_URL_PATH}?v={version}")
