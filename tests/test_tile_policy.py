"""The map layers must follow the tile providers' rules.

Since September 2026 OpenStreetMap answers apps that break its tile policy
with an "Access blocked" tile. The cards take OpenStreetMap's tiles through
Home Assistant's own proxy (core ``map_tiles``, 2026.9+) and fall back to the
one permitted direct URL -- with a Referer, which Home Assistant's page
(``<meta name="referrer" content="same-origin">``) would otherwise strip. The
nautical layers (OpenSeaMap, GEBCO, EMODnet) are cross-origin too. There are no
JS tests; this guards the lines that matter.
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(encoding="utf-8")
LAYERS = JS.split("// The map layers of both cards:", 1)[1].split("const MAP_CONTROL_CSS", 1)[0]
FILL = LAYERS.split("async function gribFillOsmBase(group, cfg, getHass) {", 1)[1].split("\n}\n", 1)[0]


def _body(name: str) -> str:
    return LAYERS.split(f"function {name}(", 1)[1].split("\n}\n", 1)[0]


def test_every_map_layer_is_created_in_one_place() -> None:
    assert JS.count("L.tileLayer(") == LAYERS.count("L.tileLayer(")
    assert JS.count("tileLayer.wms(") == LAYERS.count("tileLayer.wms(") == 1
    assert JS.count("addBaseLayers(this._map, this._config, () => this._hass);") == 2


def test_prefers_home_assistants_map_tiles_proxy() -> None:
    assert 'const HA_MAP_TILES_URL = "/api/map_tiles/raster/{z}/{x}/{y}.png?token={token}";' in JS
    assert 'hass.callWS({ type: "map_tiles/access_token" })' in JS
    # The token is renewed well inside core's 30-minute rotation.
    assert "const MAP_TILES_TOKEN_MAX_AGE_MS = 20 * 60 * 1000;" in JS
    assert FILL.index("HA_MAP_TILES_URL") < FILL.index("OSM_TILE_URL")


def test_direct_fallback_uses_the_one_permitted_osm_url() -> None:
    assert 'const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";' in JS
    assert "{s}.tile.openstreetmap.org" not in JS


def test_cross_origin_layers_send_a_referer() -> None:
    # A custom tile_url and the direct OSM fallback -- not the same-origin proxy.
    assert FILL.count("referrerPolicy: TILE_REFERRER_POLICY") == 2
    # Every WMS overlay, both OpenSeaMap tile overlays and EMODnet.
    assert "referrerPolicy: TILE_REFERRER_POLICY" in _body("gribWms")
    overlays = LAYERS.split("const MAP_OVERLAYS = [", 1)[1].split("\n];", 1)[0]
    assert overlays.count("referrerPolicy: TILE_REFERRER_POLICY") == 2
    assert _body("addBaseLayers").count("referrerPolicy: TILE_REFERRER_POLICY") == 1
    policy = re.search(r'const TILE_REFERRER_POLICY = "([^"]+)";', JS).group(1)
    # The values OpenStreetMap lists as sending a usable Referer.
    assert policy in {
        "no-referrer-when-downgrade",
        "origin",
        "origin-when-cross-origin",
        "strict-origin",
        "strict-origin-when-cross-origin",
    }


def test_layer_ids_match_the_documentation() -> None:
    overlays = re.findall(r'key: "(\w+)"', LAYERS.split("const MAP_OVERLAYS = [", 1)[1].split("\n];", 1)[0])
    assert overlays == ["gebco", "soundings", "depth", "sport", "seamarks"]
    assert 'const MAP_BASES = ["osm", "emodnet"];' in LAYERS
    assert 'const MAP_LAYERS_DEFAULT = ["seamarks"];' in LAYERS
    readme = Path("README.md").read_text(encoding="utf-8")
    for key in overlays + ["emodnet"]:
        assert f"`{key}`" in readme, key


def test_attribution_links_to_the_licences() -> None:
    for url in (
        "https://www.openstreetmap.org/copyright",
        "https://www.openseamap.org",
        "https://www.gebco.net",
        "https://emodnet.ec.europa.eu/en/bathymetry",
    ):
        assert url in LAYERS, url
