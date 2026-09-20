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
