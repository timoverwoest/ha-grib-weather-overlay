"""A run archive is unpacked while it downloads, and only what is decoded is written.

A KNMI run is 0.9 GB (Netherlands) to 3.4 GB (Europe), every hour. Saving it
and then extracting it cost twice that in SSD writes per run, some 200 GB a day
for those two datasets, for files that were read once and deleted.
"""

from __future__ import annotations

import io
from pathlib import Path
import tarfile

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grib_overlay import archive_stream, grib1, grib_decode
from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_PARAMETERS,
    CONF_SOURCE,
    CONF_STORAGE_PATH,
    DOMAIN,
)
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from custom_components.grib_overlay.sources.base import GribSourceError
from custom_components.grib_overlay.sources.knmi import KNOWN_DATASETS

from .test_grib1 import _make_grib1

DATASET = KNOWN_DATASETS[0]
WIND = next(p for p in DATASET.parameters if p.key == "wind_10m")


def _member(lead_hours: int) -> bytes:
    """One lead time as KNMI ships it: every parameter, the enabled ones and more."""
    return b"".join(
        [
            _make_grib1(param=11, level=2, bits=8, raw_values=[1] * 6, p1=lead_hours),
            _make_grib1(param=33, level=10, bits=8, raw_values=[3] * 6, p1=lead_hours),
            _make_grib1(param=34, level=10, bits=8, raw_values=[4] * 6, p1=lead_hours),
            _make_grib1(param=1, level=0, bits=8, raw_values=[9] * 6, p1=lead_hours),
        ]
    )


def _archive(*leads: int) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for lead in leads:
            data = _member(lead)
            info = tarfile.TarInfo(f"HA43_N20_202609160600_{lead:03d}00_GB")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


def test_only_the_records_of_enabled_parameters_are_kept() -> None:
    member = _member(3)
    kept = grib1.select_records(member, archive_stream.filters_for([WIND]))

    params = [m.indicator_of_parameter for m in grib1.iter_messages(kept)]
    assert params == [33, 34]
    assert len(kept) == len(member) // 2  # two of four equally sized records


def test_a_cut_down_member_decodes_the_same(tmp_path: Path) -> None:
    whole, cut = tmp_path / "whole", tmp_path / "cut"
    whole.write_bytes(_member(3))
    cut.write_bytes(
        grib1.select_records(_member(3), archive_stream.filters_for([WIND]))
    )

    a = grib_decode.decode_vector_components(whole, WIND)
    b = grib_decode.decode_vector_components(cut, WIND)
    assert (a.u == b.u).all() and (a.v == b.v).all()
    assert (a.valid_time, a.run_time) == (b.valid_time, b.run_time)


def test_a_member_past_the_horizon_is_never_written(tmp_path: Path) -> None:
    paths = archive_stream.unpack(
        io.BytesIO(_archive(3, 30)),
        tmp_path,
        archive_stream.filters_for([WIND]),
        horizon_hours=24,
    )

    assert [p.name for p in paths] == ["HA43_N20_202609160600_00300_GB"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [paths[0].name]


def test_without_filters_every_member_is_extracted_whole(tmp_path: Path) -> None:
    paths = archive_stream.unpack(io.BytesIO(_archive(3, 30)), tmp_path)

    assert [p.read_bytes() for p in paths] == [_member(3), _member(30)]


def _coordinator(hass, tmp_path: Path) -> GribOverlayCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "test-key",
            CONF_DATASET: DATASET.key,
            CONF_PARAMETERS: ["wind_10m"],
        },
        options={CONF_STORAGE_PATH: str(tmp_path)},
    )
    entry.add_to_hass(hass)
    return GribOverlayCoordinator(hass, entry)


def _chunks_of(data: bytes, size: int = 1000):
    async def _iter(dataset, filename):
        for start in range(0, len(data), size):
            yield data[start : start + size]

    return _iter


async def test_the_archive_is_unpacked_straight_off_the_download(
    hass, tmp_path: Path
) -> None:
    coordinator = _coordinator(hass, tmp_path)
    # Small chunks and a full pipe: the download has to wait for the reader.
    coordinator.source.async_iter_file = _chunks_of(_archive(*range(0, 40, 3)), 700)
    raw_dir = coordinator._scratch_root / "run"

    paths = await coordinator._async_stream_archive(
        DATASET, "run.tar", raw_dir, [WIND], horizon_hours=24
    )

    assert len(paths) == 9  # leads 0, 3, ... 24
    written = await hass.async_add_executor_job(_written, tmp_path)
    # Nothing else of the archive was written anywhere under the storage root,
    # and of each member only the wind records.
    assert sorted(written) == sorted(paths)
    assert all(params == [33, 34] for params in written.values())


def _written(root: Path) -> dict[Path, list[int]]:
    """Every file under ``root`` with the GRIB parameters it holds."""
    return {
        path: [m.indicator_of_parameter for m in grib1.iter_messages(path.read_bytes())]
        for path in root.rglob("*")
        if path.is_file()
    }


async def test_a_failed_download_reports_its_own_error(hass, tmp_path: Path) -> None:
    coordinator = _coordinator(hass, tmp_path)
    archive = _archive(0, 3, 6)

    async def _breaks_halfway(dataset, filename):
        yield archive[: len(archive) // 2]
        raise GribSourceError("connection reset")

    coordinator.source.async_iter_file = _breaks_halfway

    with pytest.raises(GribSourceError, match="connection reset"):
        await coordinator._async_stream_archive(
            DATASET, "run.tar", tmp_path / "raw", [WIND], horizon_hours=24
        )


async def test_a_reader_that_gives_up_stops_the_download(hass, tmp_path: Path) -> None:
    coordinator = _coordinator(hass, tmp_path)
    sent = 0

    async def _endless_garbage(dataset, filename):
        nonlocal sent
        while True:
            sent += 1
            yield b"not a tar archive " * 1000

    coordinator.source.async_iter_file = _endless_garbage

    with pytest.raises(tarfile.ReadError):
        await coordinator._async_stream_archive(
            DATASET, "run.tar", tmp_path / "raw", [WIND], horizon_hours=24
        )
    assert sent < 100
