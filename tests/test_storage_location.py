"""Where the working files go: the network storage in Home Assistant, for all sources.

A NAS added under Settings > System > Storage spares the local SSD the writes,
and Supervisor leaves network storage out of every backup.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grib_overlay import (
    _async_reload_entry,
    field_grid,
    storage_paths,
)
from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_FORECAST_HORIZON_HOURS,
    CONF_PARAMETERS,
    CONF_RETAIN_RUNS,
    CONF_SOURCE,
    CONF_STORAGE_APPLY_ALL,
    CONF_STORAGE_PATH,
    CONF_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)
from custom_components.grib_overlay.http import _read_for_transfer
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

NAS = {"/share/nas_data/grib_overlay": "nas_data (/share/nas_data)"}
FORM = {
    CONF_FORECAST_HORIZON_HOURS: 24,
    CONF_RETAIN_RUNS: 2,
    CONF_UPDATE_INTERVAL_MINUTES: 30,
}


def _entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


def _offered(result) -> list[str]:
    for key, value in result["data_schema"].schema.items():
        if key == CONF_STORAGE_PATH:
            return [o["value"] for o in value.config["options"]]
    raise AssertionError("no storage field in the form")


async def test_the_network_storage_is_offered_and_stored(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    with (
        patch.object(
            storage_paths, "async_network_storages", AsyncMock(return_value=dict(NAS))
        ),
        patch.object(storage_paths, "prepare_root", return_value=True),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert _offered(result) == list(NAS)

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**FORM, CONF_STORAGE_PATH: next(iter(NAS))}
        )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_STORAGE_PATH] == "/share/nas_data/grib_overlay"
    assert CONF_STORAGE_APPLY_ALL not in result["data"]


async def test_a_typed_in_path_in_use_stays_offered(hass: HomeAssistant) -> None:
    entry = _entry(hass, **{CONF_STORAGE_PATH: "/media/elsewhere"})
    with patch.object(
        storage_paths, "async_network_storages", AsyncMock(return_value=dict(NAS))
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert _offered(result) == [*NAS, "/media/elsewhere"]


async def test_one_form_can_move_every_source(hass: HomeAssistant, tmp_path) -> None:
    this, other, already = _entry(hass), _entry(hass), _entry(hass)
    hass.config_entries.async_update_entry(
        already, options={CONF_STORAGE_PATH: str(tmp_path)}
    )

    result = await hass.config_entries.options.async_init(this.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**FORM, CONF_STORAGE_PATH: str(tmp_path), CONF_STORAGE_APPLY_ALL: True},
    )

    assert result["type"] == "create_entry"
    for entry in (this, other, already):
        assert entry.options[CONF_STORAGE_PATH] == str(tmp_path)


async def test_without_the_tick_only_this_source_moves(
    hass: HomeAssistant, tmp_path
) -> None:
    this, other = _entry(hass), _entry(hass)

    result = await hass.config_entries.options.async_init(this.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {**FORM, CONF_STORAGE_PATH: str(tmp_path)}
    )

    assert this.options[CONF_STORAGE_PATH] == str(tmp_path)
    assert CONF_STORAGE_PATH not in other.options


async def test_a_folder_that_cannot_be_written_is_refused(
    hass: HomeAssistant, tmp_path
) -> None:
    entry = _entry(hass)
    blocker = tmp_path / "a-file"
    await hass.async_add_executor_job(blocker.write_text, "")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**FORM, CONF_STORAGE_PATH: str(blocker / "grib_overlay")}
    )

    assert result["type"] == "form"
    assert result["errors"] == {CONF_STORAGE_PATH: "storage_not_writable"}
    assert CONF_STORAGE_PATH not in entry.options


def _mount(name: str, usage: str, *, read_only: bool = False, path: str | None = ""):
    return SimpleNamespace(
        name=name,
        usage=usage,
        read_only=read_only,
        user_path=f"/{usage}/{name}" if path == "" else path,
    )


async def test_only_writable_shares_and_media_folders_are_listed(
    hass: HomeAssistant,
) -> None:
    mounts = [
        _mount("nas_data", "share"),
        _mount("films", "media"),
        _mount("backups", "backup", path=None),
        _mount("archive", "share", read_only=True),
    ]
    client = MagicMock()
    client.mounts.info = AsyncMock(return_value=SimpleNamespace(mounts=mounts))
    with (
        patch.object(storage_paths, "is_hassio", return_value=True),
        patch(
            "homeassistant.components.hassio.get_supervisor_client",
            return_value=client,
        ),
    ):
        found = await storage_paths.async_network_storages(hass)

    assert found == {
        "/share/nas_data/grib_overlay": "nas_data (/share/nas_data)",
        "/media/films/grib_overlay": "films (/media/films)",
    }


async def test_no_supervisor_means_no_network_storage(hass: HomeAssistant) -> None:
    assert await storage_paths.async_network_storages(hass) == {}


async def test_moving_drops_the_cache_left_at_the_old_place(
    hass: HomeAssistant, tmp_path
) -> None:
    old = tmp_path / "local" / "entry"
    new = tmp_path / "nas" / "entry"

    def _make() -> None:
        for folder in (old, storage_paths.raw_dir_for(old), new):
            folder.mkdir(parents=True)
            (folder / "f").write_text("x")
        (old.parent / "someone-elses").write_text("keep")

    await hass.async_add_executor_job(_make)
    entry = SimpleNamespace(
        title="KNMI",
        entry_id="entry",
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(storage_dir=old),
    )

    async def _reload(entry_id):
        entry.runtime_data = SimpleNamespace(storage_dir=new)
        return True

    with patch.object(hass.config_entries, "async_reload", side_effect=_reload):
        await _async_reload_entry(hass, entry)

    def _state():
        return (
            old.exists(),
            storage_paths.raw_dir_for(old).exists(),
            new.exists(),
            (old.parent / "someone-elses").exists(),
        )

    assert await hass.async_add_executor_job(_state) == (False, False, True, True)


async def test_a_reload_that_stays_put_keeps_the_cache(
    hass: HomeAssistant, tmp_path
) -> None:
    folder = tmp_path / "entry"
    await hass.async_add_executor_job(folder.mkdir)
    entry = SimpleNamespace(
        title="KNMI",
        entry_id="entry",
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(storage_dir=folder),
    )
    with patch.object(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    ):
        await _async_reload_entry(hass, entry)

    assert await hass.async_add_executor_job(folder.exists)


def test_grids_are_written_gzipped_and_read_back(tmp_path: Path) -> None:
    payload = {"nx": 2, "ny": 1, "values": [1.5, None]}
    path = tmp_path / "f.field.json.gz"

    field_grid.save_grid(path, payload)

    assert json.loads(gzip.decompress(path.read_bytes())) == payload
    assert field_grid.load_grid(path) == payload


def test_a_plain_grid_from_an_older_cache_still_reads(tmp_path: Path) -> None:
    path = tmp_path / "f.field.json"
    path.write_text(json.dumps({"nx": 1}))

    assert field_grid.load_grid(path) == {"nx": 1}


def test_a_gzipped_grid_goes_out_as_it_is(tmp_path: Path) -> None:
    path = tmp_path / "f.field.json.gz"
    field_grid.save_grid(path, {"nx": 1})

    body, encoding = _read_for_transfer(path, accepts_gzip=True)
    assert (body, encoding) == (path.read_bytes(), "gzip")
    body, encoding = _read_for_transfer(path, accepts_gzip=False)
    assert (json.loads(body), encoding) == ({"nx": 1}, None)
    # And nothing extra was written beside it.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f.field.json.gz"]
