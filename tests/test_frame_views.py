"""The frame views read their files off the event loop, and only there.

The card asks for an image, a wind grid and a scalar grid for every frame,
over and over while an animation plays. A stat per request on the event loop
stalls all of Home Assistant on slow storage (an SD card, a network mount), so
whether the file is still there is decided by the executor job that reads it.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
import inspect
from pathlib import Path
from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grib_overlay import http, render
from custom_components.grib_overlay.const import DOMAIN
from custom_components.grib_overlay.coordinator import Frame
from homeassistant.config_entries import ConfigEntryState
from homeassistant.setup import async_setup_component

T = datetime(2026, 10, 24, 6, tzinfo=UTC)

# Path methods that touch the disk. Passing one as a reference to the executor
# (``async_add_executor_job(path.exists)``) is fine; calling it is not.
BLOCKING = {"exists", "is_file", "is_dir", "stat", "read_bytes", "read_text", "open"}


def _frame(folder: Path, frame_id: str) -> Frame:
    return Frame(
        parameter_key="wind_10m",
        valid_time=T,
        run_time=T,
        png_path=folder / f"{frame_id}.png",
        bounds=(50.0, 3.0, 51.0, 4.0),
        legend=render.Legend(unit="m/s", min_value=0, max_value=1, stops=()),
        wind_path=folder / f"{frame_id}.wind.json",
        field_path=folder / f"{frame_id}.field.json",
    )


async def _client(hass, hass_client, frames: dict[str, Frame]):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(
        get_frame=lambda key, frame_id: frames.get(frame_id)
    )
    entry.mock_state(hass, ConfigEntryState.LOADED)
    assert await async_setup_component(hass, "http", {})
    for view in http.VIEWS:
        hass.http.register_view(view())
    return entry.entry_id, await hass_client()


async def test_a_cached_frame_is_served(hass, hass_client, tmp_path: Path) -> None:
    frame = _frame(tmp_path, "f1")
    frame.png_path.write_bytes(b"\x89PNG")
    frame.wind_path.write_text("[]")
    frame.field_path.write_text("{}")
    entry_id, client = await _client(hass, hass_client, {"f1": frame})

    resp = await client.get(f"/api/grib_overlay/frame/{entry_id}/wind_10m/f1.png")
    assert resp.status == 200
    assert await resp.read() == b"\x89PNG"
    resp = await client.get(f"/api/grib_overlay/wind/{entry_id}/wind_10m/f1.json")
    assert resp.status == 200
    resp = await client.get(f"/api/grib_overlay/field/{entry_id}/wind_10m/f1.json")
    assert resp.status == 200


async def test_a_frame_whose_files_are_gone_is_a_404(
    hass, hass_client, tmp_path: Path
) -> None:
    # Still in memory, but the cleanup already took its run off the disk.
    entry_id, client = await _client(hass, hass_client, {"f1": _frame(tmp_path, "f1")})

    for kind, suffix in (("frame", "png"), ("wind", "json"), ("field", "json")):
        resp = await client.get(
            f"/api/grib_overlay/{kind}/{entry_id}/wind_10m/f1.{suffix}",
            headers={"Accept-Encoding": "gzip"},
        )
        assert resp.status == 404, kind


def test_no_request_handler_touches_the_disk_itself() -> None:
    tree = ast.parse(inspect.getsource(http))
    offenders = [
        f"{fn.name}:{node.lineno} .{node.func.attr}()"
        for fn in ast.walk(tree)
        if isinstance(fn, ast.AsyncFunctionDef)
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in BLOCKING
    ]
    assert offenders == []
