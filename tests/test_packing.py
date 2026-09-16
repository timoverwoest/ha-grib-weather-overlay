"""Tests for the bit unpacker shared by the GRIB1 and GRIB2 decoders (packing.py)."""

from __future__ import annotations

import numpy as np
import pytest

from custom_components.grib_overlay.packing import MAX_BITS, unpack_bits


def _pack(values, bits: int) -> bytes:
    """Big-endian, end-to-end bit packing, done the slow obvious way."""
    bitstr = "".join(format(int(v), f"0{bits}b") for v in values)
    return np.packbits(np.array([int(c) for c in bitstr], dtype=np.uint8)).tobytes()


@pytest.mark.parametrize("bits", [1, 3, 7, 8, 9, 10, 12, 13, 16, 17, 24, 25, 31, 32, MAX_BITS])
def test_bit_unpacking_round_trips(bits) -> None:
    """Values packed end to end come back exactly, for whole-byte widths (fast
    path) and odd widths alike -- including values that straddle bytes."""
    rng = np.random.default_rng(bits)
    values = rng.integers(0, 2**bits, size=37, dtype=np.uint64)
    values[:2] = [0, 2**bits - 1]
    data = _pack(values, bits)
    unpacked = unpack_bits(data, len(values), bits)
    assert unpacked.dtype == np.uint64
    assert np.array_equal(unpacked, values)
    assert unpack_bits(data, 0, bits).size == 0


@pytest.mark.parametrize(("size", "count", "bits"), [
    (2, 2, 12),  # the last value would run into the padding
    (2, 3, 7),
    (2, 3, 16),  # whole-byte fast path
    (0, 1, 1),
])
def test_bit_unpacking_refuses_a_short_data_section(size, count, bits) -> None:
    with pytest.raises(ValueError):
        unpack_bits(b"\xff" * size, count, bits)


@pytest.mark.parametrize("bits", [0, MAX_BITS + 1, 64])
def test_bit_unpacking_refuses_unsupported_widths(bits) -> None:
    with pytest.raises(ValueError):
        unpack_bits(bytes(16), 1, bits)
