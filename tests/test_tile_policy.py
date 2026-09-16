"""The base map must follow OpenStreetMap's tile usage policy.

Since September 2026 OpenStreetMap answers apps that don't with an "Access
blocked" tile. The cards take OpenStreetMap's tiles through Home Assistant's own
proxy (core ``map_tiles``, 2026.9+) and fall back to the one permitted direct
URL -- with a Referer, which Home Assistant's page (``<meta name="referrer"
content="same-origin">``) would otherwise strip. There are no JS tests; this
guards the lines that matter.
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(encoding="utf-8")
BASE = JS.split("async function addBaseLayers(map, config, getHass) {", 1)[1].split("\n}\n", 1)[0]


def test_every_tile_layer_is_created_in_one_place() -> None:
    assert JS.count("L.tileLayer(") == BASE.count("L.tileLayer(") == 4
    assert JS.count("addBaseLayers(this._map, this._config, () => this._hass);") == 2


def test_prefers_home_assistants_map_tiles_proxy() -> None:
    assert 'const HA_MAP_TILES_URL = "/api/map_tiles/raster/{z}/{x}/{y}.png?token={token}";' in JS
    assert 'hass.callWS({ type: "map_tiles/access_token" })' in JS
    # The token is renewed well inside core's 30-minute rotation.
    assert "const MAP_TILES_TOKEN_MAX_AGE_MS = 20 * 60 * 1000;" in JS
    assert BASE.index("HA_MAP_TILES_URL") < BASE.index("OSM_TILE_URL")


def test_direct_fallback_uses_the_one_permitted_osm_url() -> None:
    assert 'const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";' in JS
    assert "{s}.tile.openstreetmap.org" not in JS


def test_cross_origin_layers_send_a_referer() -> None:
    # Seamarks, a custom tile_url and the direct OSM fallback -- not the
    # same-origin proxy.
    assert BASE.count("referrerPolicy: TILE_REFERRER_POLICY") == 3
    policy = re.search(r'const TILE_REFERRER_POLICY = "([^"]+)";', JS).group(1)
    # The values OpenStreetMap lists as sending a usable Referer.
    assert policy in {
        "no-referrer-when-downgrade",
        "origin",
        "origin-when-cross-origin",
        "strict-origin",
        "strict-origin-when-cross-origin",
    }


def test_attribution_links_to_the_licence() -> None:
    assert "https://www.openstreetmap.org/copyright" in JS
