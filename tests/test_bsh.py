"""Offline tests for BSH support: the GRIB1 record splitter (grib1.iter_records)
that regroups a multi-time current file into per-time files, and the dataset.

The live FTP download/decode path is exercised against the real BSH server
during development; here we only test the byte-level record splitting with
hand-crafted GRIB1 records (no network).
"""

from __future__ import annotations

from custom_components.grib_overlay import grib1
from custom_components.grib_overlay.sources.bsh import KNOWN_DATASETS


def _u3(n: int) -> bytes:
    return int(n).to_bytes(3, "big")


def _u2(n: int) -> bytes:
    return int(n).to_bytes(2, "big")


def _record(*, param: int, hour: int, minute: int, day: int = 24) -> bytes:
    """A minimal but valid GRIB1 record (regular lat/lon, constant field)."""
    pds = bytearray(28)
    pds[0:3] = _u3(28)
    pds[3] = 3  # table2Version
    pds[7] = 0x80  # GDS present, no BMS
    pds[8] = param
    pds[9] = 160  # indicatorOfTypeOfLevel
    pds[10:12] = _u2(1)  # level
    pds[12], pds[13], pds[14] = 26, 7, day  # yy, month, day
    pds[15], pds[16] = hour, minute
    pds[17] = 0  # unitOfTimeRange
    pds[24] = 21  # century -> 2026

    gds = bytearray(32)
    gds[0:3] = _u3(32)
    gds[4] = 255
    gds[5] = 0  # regular lat/lon
    gds[6:8] = _u2(2)  # ni
    gds[8:10] = _u2(2)  # nj
    gds[10:13] = _u3(48000)  # lat1 = 48.0
    gds[13:16] = _u3(4000)  # lon1 = 4.0
    gds[17:20] = _u3(50000)  # lat2
    gds[20:23] = _u3(6000)  # lon2
    gds[27] = 0x40  # scan +i east, +j north

    bds = bytearray(12)
    bds[0:3] = _u3(12)  # constant field (bitsPerValue == 0)

    body = bytes(pds) + bytes(gds) + bytes(bds) + b"7777"
    total = 8 + len(body)
    return b"GRIB" + _u3(total) + bytes([1]) + body


def test_iter_records_reads_times_and_raw_bytes() -> None:
    # u+v at 00:15, then u+v at 00:30 -- as in a BSH multi-time file.
    recs = [
        _record(param=49, hour=0, minute=15),
        _record(param=50, hour=0, minute=15),
        _record(param=49, hour=0, minute=30),
        _record(param=50, hour=0, minute=30),
    ]
    buf = b"".join(recs)
    out = list(grib1.iter_records(buf))
    assert len(out) == 4
    assert [(d, t) for _, d, t in out] == [
        (20260724, 15), (20260724, 15), (20260724, 30), (20260724, 30)
    ]
    # each yielded slice is exactly the original record
    assert [raw for raw, _, _ in out] == recs


def test_regroup_by_time_roundtrips_through_decoder() -> None:
    buf = b"".join([
        _record(param=49, hour=0, minute=15),
        _record(param=50, hour=0, minute=15),
        _record(param=49, hour=0, minute=30),
        _record(param=50, hour=0, minute=30),
    ])
    groups: dict[tuple[int, int], bytearray] = {}
    for rec, d, t in grib1.iter_records(buf):
        groups.setdefault((d, t), bytearray()).extend(rec)
    assert set(groups) == {(20260724, 15), (20260724, 30)}
    # a per-time file (u+v) decodes to two messages the filters can match
    per_time = bytes(groups[(20260724, 15)])
    msgs = list(grib1.iter_messages(per_time))
    assert len(msgs) == 2
    assert msgs[0].matches({"indicatorOfParameter": 49, "indicatorOfTypeOfLevel": 160, "level": 1})
    assert msgs[1].matches({"indicatorOfParameter": 50, "indicatorOfTypeOfLevel": 160, "level": 1})


def test_bsh_dataset_registered() -> None:
    ds = KNOWN_DATASETS[0]
    assert ds.grid_type == "regular_latlon"
    (current,) = ds.parameters
    assert current.kind == "vector"
    assert current.grib_filter_u["indicatorOfParameter"] == 49
    assert current.grib_filter_v["indicatorOfParameter"] == 50
