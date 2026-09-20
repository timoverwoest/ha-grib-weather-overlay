"""The GRIB Weather Overlay integration."""

from __future__ import annotations

import gzip
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .coordinator import GribOverlayCoordinator
from .http import VIEWS

_LOGGER = logging.getLogger(__name__)

FRONTEND_JS_FILENAME = "grib-overlay-card.js"
STATIC_URL_PREFIX = "/grib_overlay_static"
FRONTEND_URL_PATH = f"{STATIC_URL_PREFIX}/{FRONTEND_JS_FILENAME}"
COMPRESSIBLE_SUFFIXES = (".js", ".css")
FRONTEND_READY = f"{DOMAIN}_frontend"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the card and the API before any entry is set up.

    Home Assistant gives a custom card about two seconds to register itself and
    otherwise draws it as a "configuration error" -- one that stays until the
    page is reloaded. Registering here rather than from the first entry means a
    dashboard opened while the entries are still restoring their caches still
    gets the card file, instead of a 404 that breaks every card of this
    integration at once.
    """
    await _async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one grib_overlay config entry."""
    first_entry = DOMAIN not in hass.data
    hass.data.setdefault(DOMAIN, {})

    coordinator = GribOverlayCoordinator(hass, entry)
    # Fast, non-blocking: restore cached frames from disk, start push, schedule
    # polling. The (possibly heavy) download of a newer run happens in the
    # background so entry setup -- and the config flow -- returns immediately.
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    if first_entry:
        # Belt and braces: async_setup registers these at startup, but an entry
        # added later (or a reload after an integration error) must find them.
        await _async_register_frontend(hass)

    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{DOMAIN}-initial-refresh"
    )
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
    if hass.data.get(FRONTEND_READY):
        return
    hass.data[FRONTEND_READY] = True
    for view in VIEWS:
        hass.http.register_view(view())
    www_dir = Path(__file__).parent / "www"
    js_path = www_dir / FRONTEND_JS_FILENAME
    if not js_path.exists():
        _LOGGER.warning("Frontend card not found at %s, skipping registration", js_path)
        return
    await hass.async_add_executor_job(_refresh_precompressed, www_dir)
    # The browser must have the card before Home Assistant gives up on it (it
    # waits a couple of seconds for a custom element, then shows the card as a
    # "configuration error"). The card plus Leaflet is ~430 kB, so it is served
    # cached -- safe, because the URL below carries the version -- and gzipped.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_PREFIX, str(www_dir), cache_headers=True)]
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


def _refresh_precompressed(www_dir: Path) -> None:
    """Blocking: keep a gzipped copy beside every served .js/.css.

    aiohttp hands out ``<file>.gz`` by itself to a browser that accepts gzip,
    which cuts the card and Leaflet to about a quarter of their size. It does so
    without looking at the original, though, so a copy left over from an earlier
    version would be served in place of the new file: rebuild whatever is older
    than its source, and drop copies whose source is gone. All of it is
    best-effort -- on a read-only install the plain files are served instead.
    """
    try:
        stale = [p for p in www_dir.rglob("*.gz.tmp")]
        stale += [p for p in www_dir.rglob("*.gz") if not p.with_suffix("").is_file()]
        for path in stale:
            path.unlink(missing_ok=True)
        for path in www_dir.rglob("*"):
            if path.suffix not in COMPRESSIBLE_SUFFIXES or not path.is_file():
                continue
            gz = path.with_name(path.name + ".gz")
            if gz.is_file() and gz.stat().st_mtime >= path.stat().st_mtime:
                continue
            source = path.read_bytes()
            blob = gzip.compress(source, 9)
            if gzip.decompress(blob) != source:  # never serve a copy we can't read back
                continue
            tmp = path.with_name(path.name + ".gz.tmp")
            tmp.write_bytes(blob)
            tmp.replace(gz)
    except OSError as err:
        _LOGGER.debug("Could not pre-compress the card assets in %s: %s", www_dir, err)
