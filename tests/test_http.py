"""HTTP view tests: entries/frames/frame-image endpoints against real cached frames.

Reuses the same opt-in real-GRIB-sample setup as test_coordinator.py.
"""

from __future__ import annotations

import os
import tarfile
from pathlib import Path

import pytest
from homeassistant.setup import async_setup_component

from custom_components.grib_overlay.const import CONF_API_KEY, CONF_DATASET, CONF_PARAMETERS, CONF_SOURCE, DOMAIN
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from custom_components.grib_overlay.http import VIEWS
from pytest_homeassistant_custom_component.common import MockConfigEntry

SAMPLE_ENV_VAR = "GRIB_OVERLAY_SAMPLE_GRIB"

pytestmark = pytest.mark.skipif(
    not os.environ.get(SAMPLE_ENV_VAR), reason=f"set {SAMPLE_ENV_VAR} to a sample GRIB file to run"
)


async def test_entries_frames_and_image_endpoints(
    hass, hass_client, hass_client_no_auth, tmp_path: Path
) -> None:
    sample_path = Path(os.environ[SAMPLE_ENV_VAR])
    tar_path = tmp_path / "HARM43_V1_P1_2026071802.tar"
    with tarfile.open(tar_path, "w") as tar:
        tar.add(sample_path, arcname="HA43_N20_202607180200_00500_GB")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "unused",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
    )
    entry.add_to_hass(hass)

    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.storage_dir = tmp_path / "storage"
    from custom_components.grib_overlay.sources.knmi import KNOWN_DATASETS

    dataset = KNOWN_DATASETS[0]
    parameters = [p for p in dataset.parameters if p.key == "wind_10m"]
    run_dir = coordinator.storage_dir / tar_path.stem
    coordinator.frames = coordinator._extract_decode_and_render(
        tar_path, run_dir, parameters, horizon_hours=24
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    assert await async_setup_component(hass, "http", {})
    for view in VIEWS:
        hass.http.register_view(view())

    client = await hass_client()

    resp = await client.get("/api/grib_overlay/entries")
    assert resp.status == 200
    body = await resp.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["entry_id"] == entry.entry_id
    assert [p["key"] for p in body["entries"][0]["parameters"]] == ["wind_10m"]

    resp = await client.get(f"/api/grib_overlay/frames/{entry.entry_id}")
    assert resp.status == 200
    frames_body = await resp.json()
    assert len(frames_body["wind_10m"]) == 1
    frame_info = frames_body["wind_10m"][0]
    assert frame_info["image_url"].startswith(f"/api/grib_overlay/frame/{entry.entry_id}/wind_10m/")

    resp = await client.get(frame_info["image_url"])
    assert resp.status == 200
    assert resp.content_type == "image/png"
    png_bytes = await resp.read()
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    # The image endpoint must load without auth -- Leaflet's imageOverlay uses a
    # plain <img> that can't send HA's bearer token. (The metadata endpoints
    # above stay authenticated.)
    noauth_client = await hass_client_no_auth()
    resp = await noauth_client.get(frame_info["image_url"])
    assert resp.status == 200
    assert resp.content_type == "image/png"

    resp = await noauth_client.get(f"/api/grib_overlay/frames/{entry.entry_id}")
    assert resp.status == 401  # metadata still requires auth

    resp = await client.get(f"/api/grib_overlay/frames/unknown-entry")
    assert resp.status == 404
