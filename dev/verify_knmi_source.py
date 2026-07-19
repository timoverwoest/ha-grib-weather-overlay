#!/usr/bin/env python3
"""Standalone check of sources/knmi.py against the real KNMI Open Data API.

No Home Assistant needed -- only aiohttp. Run:

    python3 dev/verify_knmi_source.py [api_key]

If no api_key is given, KNMI's public rate-limited anonymous demo key is
used (fine for this connectivity check, not for the shipped integration --
users enter their own free key in the config flow).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiohttp

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "grib_overlay"))

from sources.knmi import KnmiSource  # noqa: E402

ANONYMOUS_DEMO_KEY = (
    "eyJvcmciOiI1ZTU1NGUxOTI3NGE5NjAwMDEyYTNlYjEiLCJpZCI6IjUzYTg1ZDBhMmQ5YzRk"
    "YzJiYWNlNzQ4NTQ2Zjk4ODExIiwiaCI6Im11cm11cjEyOCJ9"
)


async def main(api_key: str) -> None:
    async with aiohttp.ClientSession() as session:
        source = KnmiSource(session, api_key)

        datasets = await source.async_list_datasets()
        print(f"Datasets in catalog: {len(datasets)}")
        for ds in datasets:
            print(f"  - {ds.key} v{ds.version}: {ds.name}")
            print(f"    bounds={ds.bounds} grid={ds.grid_type} params={[p.key for p in ds.parameters]}")

        dataset = datasets[0]
        print(f"\nListing latest files for {dataset.key}...")
        files = await source.async_list_files(dataset, max_keys=3)
        for f in files:
            print(f"  {f.filename}  {f.size / 1_000_000:.1f} MB  modified={f.last_modified}")

        if not files:
            print("No files returned - nothing more to check.")
            return

        latest = files[0]
        print(f"\nRequesting a temporary download URL for {latest.filename}...")
        url = await source.async_get_download_url(dataset, latest.filename)
        print(f"  got a signed URL ({len(url)} chars) - OK, not downloading the full {latest.size / 1_000_000:.0f} MB file here.")


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else ANONYMOUS_DEMO_KEY
    asyncio.run(main(key))
