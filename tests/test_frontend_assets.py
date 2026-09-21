"""The card has to reach the browser before Home Assistant gives up on it.

Home Assistant waits a couple of seconds for a custom element to appear and
otherwise draws the card as a "configuration error". The card plus the vendored
Leaflet is some 430 kB, so the folder is served with cache headers -- safe,
because every URL carries the integration version -- and with a gzipped copy
beside each file, which aiohttp hands out by itself to browsers that accept it.
"""

from __future__ import annotations

import gzip
import os
from pathlib import Path

import pytest

from custom_components.grib_overlay import _refresh_precompressed

INIT = Path("custom_components/grib_overlay/__init__.py").read_text(encoding="utf-8")
JS = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(encoding="utf-8")


def test_static_assets_are_cached_under_a_versioned_url() -> None:
    assert "StaticPathConfig(STATIC_URL_PREFIX, str(www_dir), cache_headers=True)" in INIT
    assert 'add_extra_js_url(hass, f"{FRONTEND_URL_PATH}?v={version}")' in INIT
    # The vendored files the card loads itself must carry the same version, or a
    # month-long cache would keep serving the Leaflet from before an update.
    assert "const GRIB_ASSET_QUERY" in JS
    for name in ("LEAFLET_JS_URL", "LEAFLET_CSS_URL", "VELOCITY_JS_URL", "VELOCITY_CSS_URL"):
        line = next(line for line in JS.splitlines() if line.startswith(f"const {name} ="))
        assert line.endswith("${GRIB_ASSET_QUERY}`;"), line


def test_a_gzipped_copy_is_made_for_every_served_asset(tmp_path: Path) -> None:
    (tmp_path / "vendor").mkdir()
    (tmp_path / "card.js").write_text("x" * 5000)
    (tmp_path / "vendor" / "leaflet.css").write_text("y" * 5000)
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")

    _refresh_precompressed(tmp_path)

    assert gzip.decompress((tmp_path / "card.js.gz").read_bytes()) == b"x" * 5000
    assert (tmp_path / "vendor" / "leaflet.css.gz").is_file()
    assert not (tmp_path / "logo.png.gz").exists()


def test_a_copy_older_than_its_source_is_rebuilt(tmp_path: Path) -> None:
    card = tmp_path / "card.js"
    card.write_text("old")
    _refresh_precompressed(tmp_path)
    gz = tmp_path / "card.js.gz"
    os.utime(gz, (0, 0))  # as if it were left behind by the previous version
    card.write_text("new")

    _refresh_precompressed(tmp_path)
    assert gzip.decompress(gz.read_bytes()) == b"new"

    # An unchanged file is not rewritten on every restart.
    before = gz.stat().st_mtime_ns
    _refresh_precompressed(tmp_path)
    assert gz.stat().st_mtime_ns == before


def test_copies_without_a_source_and_half_written_ones_are_removed(tmp_path: Path) -> None:
    (tmp_path / "gone.js.gz").write_bytes(gzip.compress(b"a card from an older version"))
    (tmp_path / "card.js.gz.tmp").write_bytes(b"half written")
    (tmp_path / "card.js").write_text("hello")

    _refresh_precompressed(tmp_path)

    assert not (tmp_path / "gone.js.gz").exists()
    assert not (tmp_path / "card.js.gz.tmp").exists()
    assert (tmp_path / "card.js.gz").is_file()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the read-only bit")
def test_a_read_only_install_still_serves_the_plain_files(tmp_path: Path) -> None:
    (tmp_path / "card.js").write_text("hello")
    tmp_path.chmod(0o500)
    try:
        _refresh_precompressed(tmp_path)  # must not raise
    finally:
        tmp_path.chmod(0o700)
    assert not (tmp_path / "card.js.gz").exists()


def test_a_throwing_hass_setter_cannot_blank_the_card() -> None:
    """Home Assistant replaces a card whose `hass` setter throws with a bare
    "configuration error" -- no message, nothing to go on. Every setter guards
    its body, so a hiccup costs a frame and not the card."""
    assert JS.count("set hass(hass) {") == JS.count('gribGuard("hass update", () => {') == 3
    for block in JS.split("set hass(hass) {")[1:]:
        body = block.split("\n  }\n", 1)[0]
        assert 'gribGuard("hass update"' in body
        # Only the bookkeeping line may sit outside the guard.
        before = body.split("gribGuard", 1)[0].strip()
        assert before == "this._hass = hass;", before


def test_the_card_announces_itself_with_its_version() -> None:
    """The banner is the answer to "is the card loaded, and which version?" --
    it runs last, so a console without it means the file never finished."""
    assert "GRIB-OVERLAY-CARD %c ${GRIB_ASSET_VERSION" in JS
    banner = JS.index("console.info(")
    assert banner > JS.index('gribDefineCard("grib-overlay-weathermap-card"')
    assert JS[banner:].count("gribDefineCard(") == 0


def test_a_re_attached_card_fetches_its_frames_again() -> None:
    """Home Assistant keeps a view's cards in memory, so browsing back re-attaches
    the same element. It must not need a page reload to show a map again."""
    connected = JS.split("  connectedCallback() {", 1)[1].split("\n  }\n", 1)[0]
    assert "this._refreshAfterReattach();" in connected
    body = JS.split("  async _refreshAfterReattach() {", 1)[1].split("\n  }\n", 1)[0]
    assert "await this._onParameterChange();" in body
    assert "if (back > 0) this._showFrame(back);" in body  # same moment as before
    assert "invalidateSize()" in body


def test_the_card_is_served_before_any_entry_is_set_up() -> None:
    """A dashboard opened while the entries are still restoring their caches
    must not get a 404 for the card: that breaks every card of this integration
    at once, until the page is reloaded."""
    assert "async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:" in INIT
    setup = INIT.split("async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:", 1)[1]
    setup = setup.split("\nasync def ", 1)[0]
    assert "await _async_register_frontend(hass)" in setup
    # Registering twice would raise, so it is guarded and does the views too.
    register = INIT.split("async def _async_register_frontend(hass: HomeAssistant) -> None:", 1)[1]
    register = register.split("\ndef ", 1)[0]
    assert "if hass.data.get(FRONTEND_READY):" in register
    assert "hass.http.register_view(view())" in register


def test_a_gzip_copy_that_cannot_be_read_back_is_not_written(tmp_path: Path) -> None:
    # aiohttp serves the .gz in place of the file, without ever looking at the
    # original: a copy we cannot decompress ourselves must never reach disk.
    refresh = INIT.split("def _refresh_precompressed(www_dir: Path) -> None:", 1)[1]
    assert "if gzip.decompress(blob) != source:" in refresh


def test_a_blank_map_is_measured_again_and_rebuilt_if_needed() -> None:
    """Switching dashboards can hand the card back with nothing painted: the
    controls and data are there, the map area is empty."""
    body = JS.split("  async _ensureTilesOnce(allowRebuild) {", 1)[1].split("\n  }\n", 1)[0]
    assert "for (const wait of [250, 750, 1500, 3000])" in body
    assert "layer.redraw()" in body  # tiles that were dropped have to be drawn again
    assert "if (this._rebuilds > 2) return;" in body  # and never in a loop
    assert "this._map.invalidateSize({ pan: false });" in body
    assert "await this._initialize();" in body  # last resort: build the map again
    assert "this._map.setView(center, zoom);" in body  # at the same place
    # The image overlay is recreated when its image is no longer on the map --
    # setUrl on a detached image paints nothing.
    assert "if (this._imageOverlay && !this._map.hasLayer(this._imageOverlay))" in JS
    assert "!this._imageOverlay.getElement()?.isConnected" in JS


def test_the_card_finds_its_own_url_when_loaded_as_a_module() -> None:
    """Home Assistant imports the card, it does not add a <script src> tag, so
    there is nothing to query: without the stack-trace fallback the banner says
    "dev" and the vendored files lose their cache-busting version."""
    block = JS.split("const GRIB_ASSET_URL = (() => {", 1)[1].split("})();", 1)[0]
    assert "document.currentScript?.src" in block
    assert "new Error().stack" in block
    assert 'replace(/:\\d+:\\d+$/, "")' in block  # a stack entry ends in :line:column


def test_the_dataset_fit_waits_until_the_card_has_a_size() -> None:
    """A card built while its dashboard page is still hidden has a zero-size map.
    Fitting the dataset into that lands on zoom 0 -- a world map with a speck of
    overlay, which is what an "empty" card on another page turns out to be."""
    fit = JS.split("  _fitBounds(bounds) {", 1)[1].split("\n  }\n", 1)[0]
    assert "if (!this._els.mapDiv.offsetWidth || !this._els.mapDiv.offsetHeight) {" in fit
    assert "this._pendingFit = bounds;" in fit
    # ... and it is honoured as soon as there is a size, from the resize
    # observer and from the tile check.
    observer = JS.split("    this._resizeObserver = new ResizeObserver(() => {", 1)[1]
    assert "this._applyPendingFit();" in observer.split("});", 1)[0]
    assert "if (this._applyPendingFit()) return;" in JS
    # The fit is only marked done when it actually happened.
    apply = JS.split("  _applyPendingFit() {", 1)[1].split("\n  }\n", 1)[0]
    assert "this._boundsFit = true;" in apply and "this._map.fitBounds(bounds);" in apply


def test_the_banner_says_how_the_card_was_loaded() -> None:
    """When the "configuration error" placeholder does turn up, the next question
    is whether the file was slow, cached, or never fetched at all."""
    body = JS.split("function gribLoadTiming() {", 1)[1].split("\n}\n", 1)[0]
    assert "performance.getEntriesByName(GRIB_ASSET_URL)[0]" in body
    assert '"from cache"' in body
    assert "loaded in ${Math.round(entry.duration)} ms" in body
    assert "gribLoadTiming()" in JS.split("console.info(", 1)[1]


def test_a_second_copy_of_the_card_does_not_take_the_file_down() -> None:
    """Defining a tag twice throws, and that throw would leave the cards defined
    further down the file unregistered -- every one of them a "configuration
    error". A duplicate copy (a cached older version, a Lovelace resource on top
    of the integration) has to be survivable."""
    assert JS.count("customElements.define(") == 1  # only inside the guard
    body = JS.split("function gribDefineCard(tag, cls) {", 1)[1].split("\n}\n", 1)[0]
    assert "const existing = customElements.get(tag);" in body
    assert "console.warn(" in body
    for tag in ("grib-overlay-card", "grib-overlay-compare-card", "grib-overlay-weathermap-card"):
        assert f'gribDefineCard("{tag}"' in JS


def test_a_blank_configuration_error_is_reported_back_to_home_assistant() -> None:
    """The only account of a message-less "configuration error" is the line the
    frontend writes to the browser console just before it -- the card type and
    the error. On a phone there is no console to read it in, so the card takes a
    copy and posts it to the integration, which logs it and shows it."""
    body = JS.split("function gribWatchForCardErrors() {", 1)[1].split("\n}\n", 1)[0]
    # Home Assistant's own line, and nothing else: matching our own warnings
    # would put the hook in a loop with itself.
    assert 'first.startsWith("custom:grib-overlay-")' in body
    assert "window.__gribOverlayErrorHook" in body  # a second copy must not hook twice
    assert "original.apply(this, args)" in body  # the console still gets the line
    assert 'const GRIB_REPORT_PATH = "grib_overlay/client_error";' in JS
    assert 'hass.callApi("POST", GRIB_REPORT_PATH' in JS
    # A card that throws on every state change would otherwise post endlessly.
    assert "gribReportsSent >= GRIB_REPORT_MAX" in JS
    # Reporting failures with console.error would feed the hook its own output.
    send = JS.split("async function gribSendReport() {", 1)[1].split("\n}\n", 1)[0]
    assert "console.warn(" in send and "console.error(" not in send


def test_a_report_says_what_state_the_card_was_in() -> None:
    """A `hass` assignment throws for three reasons, and each one shows up in
    the element: a getter without a setter, a frozen element, or an element
    built by an older copy of the file. Look while it is still there."""
    body = JS.split("function gribElementState(el) {", 1)[1].split("\n}\n", 1)[0]
    assert "getter without a setter" in body
    assert "Object.isFrozen(el)" in body
    assert "customElements.get(tag) === el.constructor" in body
    assert "gribNavigationType" in JS  # "reload" is not the same failure as "navigate"
    assert "window.__gribOverlayLoads" in JS  # a second copy changes every other clue


def test_a_card_nobody_can_see_stops_animating() -> None:
    """Home Assistant keeps the cards of a view it is not showing. The particle
    layer is a requestAnimationFrame loop, so a few of these would spend the
    browser's animation budget on cards nobody is looking at."""
    body = JS.split("  _setWindAnimation(running) {", 1)[1].split("\n  }\n", 1)[0]
    assert "layer._clearWind()" in body
    # Leaflet goes on drawing, and the layer restarts itself 750 ms after every
    # draw: stopping the loop once is not enough.
    assert "layer._startWindy = () => {};" in body
    assert "delete layer._startWindy;" in body
    awake = JS.split("  _setAwake(awake) {", 1)[1].split("\n  }\n", 1)[0]
    assert "this._setWindAnimation(awake)" in awake
    assert "this._suspendPlayback()" in awake and "this._resumePlayback()" in awake
    watch = JS.split("  _watchVisibility() {", 1)[1].split("\n  }\n", 1)[0]
    assert "new IntersectionObserver(" in watch
    assert 'document.addEventListener("visibilitychange"' in watch
    assert 'document.removeEventListener("visibilitychange"' in JS
    assert "this._visibilityObserver.disconnect();" in JS


def test_the_playback_button_keeps_its_place_while_the_card_sleeps() -> None:
    """Coming back to the page should find the animation running, so pausing
    off-screen must not look like the user pressing stop."""
    suspend = JS.split("  _suspendPlayback() {", 1)[1].split("\n  }\n", 1)[0]
    assert "playPauseBtn" not in suspend
    assert "this._playbackSuspended = true;" in suspend
    resume = JS.split("  _resumePlayback() {", 1)[1].split("\n  }\n", 1)[0]
    assert "this._startPlaybackTimer();" in resume


def test_the_chart_card_does_not_poll_for_a_page_nobody_has_open() -> None:
    """Ten minutes apart, for every hidden dashboard page, over Nabu Casa."""
    body = JS.split("  async _load(refresh = false) {", 1)[1].split("\n  }\n", 1)[0]
    assert "if (refresh && !this._isVisible()) {" in body
    assert "this._missedRefresh = true;" in body
    assert "this._missedRefresh && this._load(true)" in JS  # caught up on return
