"""End-to-end test of async_setup_entry/async_unload_entry against mocked KNMI responses.

Uses a real GRIB sample (see test_coordinator.py) packed into a fake tar so
the coordinator's first refresh genuinely downloads, extracts, decodes and
renders through the exact code path __init__.py wires up.
"""

from __future__ import annotations

import os
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from custom_components.grib_overlay.const import CONF_API_KEY, CONF_DATASET, CONF_PARAMETERS, CONF_SOURCE, DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

SAMPLE_ENV_VAR = "GRIB_OVERLAY_SAMPLE_GRIB"

pytestmark = pytest.mark.skipif(
    not os.environ.get(SAMPLE_ENV_VAR), reason=f"set {SAMPLE_ENV_VAR} to a sample GRIB file to run"
)

FILES_URL = (
    "https://api.dataplatform.knmi.nl/open-data/v1/datasets/"
    "harmonie_arome_cy43_p1/versions/1.0/files"
)
FILE_URL_ENDPOINT = (
    "https://api.dataplatform.knmi.nl/open-data/v1/datasets/"
    "harmonie_arome_cy43_p1/versions/1.0/files/HARM43_V1_P1_2026071802.tar/url"
)
DOWNLOAD_URL = "https://example-download.knmi.nl/HARM43_V1_P1_2026071802.tar"


def _build_tar_bytes(sample_path: Path) -> bytes:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        tar.add(sample_path, arcname="HA43_N20_202607180200_00500_GB")
    return buf.getvalue()


async def test_setup_and_unload_entry(hass, aioclient_mock, tmp_path: Path) -> None:
    sample_path = Path(os.environ[SAMPLE_ENV_VAR])
    tar_bytes = _build_tar_bytes(sample_path)

    aioclient_mock.get(
        FILES_URL,
        json={
            "files": [
                {
                    "filename": "HARM43_V1_P1_2026071802.tar",
                    "size": len(tar_bytes),
                    "lastModified": "2026-07-18T04:33:39+00:00",
                }
            ]
        },
    )
    aioclient_mock.get(FILE_URL_ENDPOINT, json={"temporaryDownloadUrl": DOWNLOAD_URL})
    aioclient_mock.get(DOWNLOAD_URL, content=tar_bytes)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "test-key",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m", "pressure_msl"],
        },
    )
    entry.add_to_hass(hass)

    # Route the coordinator's on-disk cache into tmp_path instead of the real config dir.
    hass.config.config_dir = str(tmp_path)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Setup no longer blocks on the download -- the first refresh runs in the
    # background. Await one explicitly so the frames are ready to assert on.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert set(coordinator.frames.keys()) == {"wind_10m", "pressure_msl"}
    assert len(coordinator.frames["wind_10m"]) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
