"""Coordinator extraction/decode/render pipeline test using a real GRIB sample.

Downloading a HARMONIE run isn't something CI/dev should do on every run (one
run is ~850MB), so this test is opt-in: point GRIB_OVERLAY_SAMPLE_GRIB at a
single extracted lead-time GRIB file (see dev/verify_knmi_source.py +
dev/render_preview.py's docstring for how to obtain one) and it will be
packed into a throwaway tar and run through the coordinator's real
extract/decode/render path. Skipped otherwise.
"""

from __future__ import annotations

import os
import tarfile
from pathlib import Path

import pytest

from custom_components.grib_overlay.const import CONF_API_KEY, CONF_DATASET, CONF_PARAMETERS, CONF_SOURCE, DOMAIN
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

SAMPLE_ENV_VAR = "GRIB_OVERLAY_SAMPLE_GRIB"

pytestmark = pytest.mark.skipif(
    not os.environ.get(SAMPLE_ENV_VAR), reason=f"set {SAMPLE_ENV_VAR} to a sample GRIB file to run"
)


async def test_extract_decode_and_render_produces_frames(hass, tmp_path: Path) -> None:
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
            CONF_PARAMETERS: ["wind_10m", "temperature_2m", "pressure_msl"],
        },
    )
    entry.add_to_hass(hass)

    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.storage_dir = tmp_path / "storage"

    from custom_components.grib_overlay.sources.knmi import KNOWN_DATASETS

    dataset = KNOWN_DATASETS[0]
    parameters = [p for p in dataset.parameters if p.key in entry.data[CONF_PARAMETERS]]

    run_dir = coordinator.storage_dir / tar_path.stem
    frames = coordinator._extract_decode_and_render(tar_path, run_dir, parameters, horizon_hours=24)

    assert set(frames.keys()) == {"wind_10m", "temperature_2m", "pressure_msl"}
    for key, frame_list in frames.items():
        assert len(frame_list) == 1, f"expected exactly one lead time decoded for {key}"
        frame = frame_list[0]
        assert frame.png_path.exists()
        assert frame.png_path.stat().st_size > 0
        south, west, north, east = frame.bounds
        assert south < north and west < east
        assert frame.legend.min_value < frame.legend.max_value

    # the extracted member file should have been cleaned up after processing
    assert not any(p.name.startswith("HA43_") for p in run_dir.iterdir())

    # A fresh coordinator (as after a restart) must rebuild the same frames from
    # the on-disk manifest without re-downloading/re-rendering.
    assert (run_dir / "frames.json").exists()
    fresh = GribOverlayCoordinator(hass, entry)
    fresh.storage_dir = coordinator.storage_dir
    run_filename, cached = fresh._load_cached_frames()
    assert run_filename == tar_path.name
    assert set(cached.keys()) == {"wind_10m", "temperature_2m", "pressure_msl"}
    for key, frame_list in cached.items():
        assert len(frame_list) == 1
        assert frame_list[0].png_path.exists()
        assert frame_list[0].bounds == frames[key][0].bounds
        assert frame_list[0].legend.min_value == frames[key][0].legend.min_value
