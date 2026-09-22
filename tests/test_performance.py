"""What the card costs to show: bytes over the wire, waiting, and bursts.

Measured on a real instance with fourteen configured sources: one visit to a
dashboard page fetched 533 kB over nine requests, the wind grid alone was 213 kB
of uncompressed JSON, the chart listing blocked the page for two seconds, and
the same frame list was fetched three times.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import time
from pathlib import Path

import pytest

from custom_components.grib_overlay import weather_maps
from custom_components.grib_overlay.http import _read_for_transfer

JS = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(encoding="utf-8")


def _grid(tmp_path: Path) -> Path:
    """A grid the size of the ones a real instance serves: 16900 numbers."""
    path = tmp_path / "wind_10m_20260922T1200.json"
    path.write_text(json.dumps([{"header": {"nx": 130, "ny": 130}, "data": [round(i % 30 - 15 + 0.25, 2) for i in range(16900)]}]))
    return path


def test_a_grid_goes_over_the_wire_compressed(tmp_path: Path) -> None:
    """Tens of thousands of numbers written out as text: four times smaller
    compressed, and the biggest thing the card ever downloads."""
    path = _grid(tmp_path)
    body, encoding = _read_for_transfer(path, accepts_gzip=True)
    assert encoding == "gzip"
    assert gzip.decompress(body) == path.read_bytes()
    assert len(body) * 2 < path.stat().st_size, "compression should more than halve it"


def test_the_compressed_copy_is_kept_beside_the_file(tmp_path: Path) -> None:
    """Written once, read for every frame the user scrubs through."""
    path = _grid(tmp_path)
    first, _ = _read_for_transfer(path, accepts_gzip=True)
    gz = path.with_name(path.name + ".gz")
    assert gz.is_file()
    gz.write_bytes(first)  # touch it so its mtime is clearly newer
    second, _ = _read_for_transfer(path, accepts_gzip=True)
    assert second == first
    assert not list(tmp_path.glob("*.gz.tmp")), "no half-written copies left behind"


def test_a_stale_compressed_copy_is_not_served(tmp_path: Path) -> None:
    """A new run writes a new grid; the copy beside it is from the old one."""
    path = _grid(tmp_path)
    _read_for_transfer(path, accepts_gzip=True)
    path.write_text(json.dumps([{"header": {"nx": 1, "ny": 1}, "data": [42.0]}]))
    body, encoding = _read_for_transfer(path, accepts_gzip=True)
    assert json.loads(gzip.decompress(body))[0]["data"] == [42.0]


def test_a_browser_that_cannot_take_gzip_gets_the_file(tmp_path: Path) -> None:
    path = _grid(tmp_path)
    body, encoding = _read_for_transfer(path, accepts_gzip=False)
    assert encoding is None and body == path.read_bytes()


def test_a_read_only_cache_still_gets_a_compressed_response(tmp_path: Path) -> None:
    path = _grid(tmp_path)
    tmp_path.chmod(0o500)
    try:
        body, encoding = _read_for_transfer(path, accepts_gzip=True)
    finally:
        tmp_path.chmod(0o700)
    assert encoding == "gzip" and gzip.decompress(body) == path.read_bytes()


def test_the_card_caches_the_request_not_the_answer() -> None:
    """Filling a cache after the await means two callers that both ask before
    the first is back each fetch the file -- which is how one page load came to
    download the same frame list three times."""
    for method in ("async _fetchJson(url, cache) {", "async _fetchWind(url) {", "async _fetchParamFrames(paramKey) {"):
        body = JS.split(method, 1)[1].split("\n  }\n", 1)[0]
        assert "const pending = this._hass" in body, method
        assert "pending.catch(" in body, f"{method}: a failure must not be remembered"
        assert "return pending;" in body, method


async def test_the_charts_a_card_already_has_are_served_at_once(hass) -> None:
    """Listing and fetching them takes seconds against KNMI, and charts change
    every few hours: a list ten minutes old is still the right answer."""
    maps = weather_maps.WeatherMaps(hass)
    known = [weather_maps.Chart("AL_202609221800.gif", "analysis", weather_maps.datetime.now(weather_maps.timezone.utc), "x")]
    maps._charts, maps._listed_at = known, time.monotonic() - weather_maps._LIST_TTL_SECONDS - 1

    refreshed = asyncio.Event()

    async def slow_refresh():
        await asyncio.sleep(5)
        refreshed.set()
        return known

    maps._refresh = slow_refresh
    started = time.monotonic()
    charts = await maps.charts()
    assert charts is known
    assert time.monotonic() - started < 1, "a stale list must not make the card wait"
    assert maps._refreshing is not None, "and the new one is fetched behind it"
    maps._refreshing.cancel()


async def test_a_card_with_nothing_to_show_waits_for_the_charts(hass) -> None:
    maps = weather_maps.WeatherMaps(hass)

    async def refresh():
        maps._charts = ["something"]
        return maps._charts

    maps._refresh = refresh
    assert await maps.charts() == ["something"]


async def test_every_source_polls_in_its_own_slot(hass) -> None:
    """Home Assistant starts them all within the same second, so their timers
    line up: a dozen providers hit, and a dozen decodes started, on the same
    second of every half hour."""
    from custom_components.grib_overlay.const import (
        CONF_API_KEY,
        CONF_DATASET,
        CONF_PARAMETERS,
        CONF_SOURCE,
        DOMAIN,
    )
    from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    def coordinator_for(entry_id: str) -> GribOverlayCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id=entry_id,
            data={
                CONF_SOURCE: "knmi",
                CONF_API_KEY: "test-key",
                CONF_DATASET: "harmonie_arome_cy43_p1",
                CONF_PARAMETERS: ["wind_10m"],
            },
        )
        entry.add_to_hass(hass)
        return GribOverlayCoordinator(hass, entry)

    ids = ("01KXXR63PBA5JRBGJ7BDZZ0HS8", "01M2NZQCGMA8HRYZMZZGEYK456", "01M2NZR1SAQ4XZK437ZW2B1HYF")
    offsets = [coordinator_for(i)._poll_offset for i in ids]
    assert len(set(offsets)) == len(ids), "different entries, different slots"
    assert all(0 <= o < 600 for o in offsets), offsets
    # The same entry lands in the same slot after a restart, so the spread holds.
    assert coordinator_for(ids[0])._poll_offset == offsets[0]


def test_the_cards_on_a_page_share_one_list_of_sources() -> None:
    """Each card asking for itself meant the same 13 kB, and a round trip for
    it, once per card on the page."""
    body = JS.split("function gribFetchEntries(hass) {", 1)[1].split("\n}\n", 1)[0]
    assert "gribEntriesRequest = hass.callApi" in body
    assert "GRIB_ENTRIES_TTL_MS" in body
    assert "gribEntriesRequest = null" in body  # a failure must not be remembered
    assert "(data.entries || []).slice()" in body  # a card may sort and filter its own copy
    assert JS.count('callApi("GET", "grib_overlay/entries")') == 1
    assert JS.count("gribFetchEntries(this._hass)") == 2


def test_the_lists_are_compressed_too() -> None:
    """A frame list for one entry is 49 kB of timestamps and urls, built in
    memory so there is no file to keep a compressed copy beside."""
    from custom_components.grib_overlay.http import _COMPRESS_FROM_BYTES, _json

    class _Request:
        def __init__(self, accept): self.headers = {"Accept-Encoding": accept}

    big = {"frames": [{"valid_time": f"2026-09-22T{h:02d}:00:00+00:00", "url": "/api/x" * 20} for h in range(24)] * 12}
    compressed = _json(_Request("gzip, deflate"), big)
    assert compressed.headers["Content-Encoding"] == "gzip"
    assert len(gzip.decompress(compressed.body)) > 3 * len(compressed.body)
    # Below a few kB the header costs more than the saving.
    small = _json(_Request("gzip"), {"error": "unknown entry_id"})
    assert "Content-Encoding" not in small.headers
    assert json.loads(small.body) == {"error": "unknown entry_id"}
    # And a caller that cannot take it gets plain JSON whatever the size.
    plain = _json(_Request(""), big)
    assert "Content-Encoding" not in plain.headers
    assert len(plain.body) >= _COMPRESS_FROM_BYTES


def test_the_next_frame_is_only_fetched_when_it_will_be_wanted() -> None:
    """These images are well over a hundred kilobytes. Prefetching the next one
    on a page that is only being looked at doubled what the card downloaded."""
    body = JS.split("  _showFrame(index) {", 1)[1].split("\n  }\n", 1)[0]
    assert "if (this._playTimer || this._steppedThroughTime) {" in body
    assert JS.count("this._steppedThroughTime = true;") == 2  # both sliders
