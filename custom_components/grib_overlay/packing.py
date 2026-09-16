"""Bit unpacking for GRIB grid-point simple packing, shared by grib1.py and grib2.py.

Both editions store the packed values the same way: unsigned integers of a
fixed bit width, big-endian, end to end. Only the scaling around them differs.
"""

from __future__ import annotations

import numpy as np

# Widest value that, starting anywhere in a byte, still fits in one 8-byte window.
MAX_BITS = 57

_WHOLE_BYTES = {8: ">u1", 16: ">u2", 32: ">u4"}


def unpack_bits(data: bytes, count: int, bits: int) -> np.ndarray:
    """``count`` big-endian unsigned integers of ``bits`` bits each, packed end to end.

    Reads, for every value, the 8 bytes starting at its first byte as one
    64-bit word and shifts the value out of it -- a few arrays of ``count``
    words, instead of one row of ``bits`` bits per value (~200 MB for a single
    ICON-D2 field).

    Raises ValueError for a width over MAX_BITS, or a data section too short
    to hold ``count`` values (rather than reading the padding as zeros).
    """
    if not 0 < bits <= MAX_BITS:
        raise ValueError(f"unsupported bits per value: {bits}")
    if len(data) * 8 < count * bits:
        raise ValueError(f"data section holds fewer than {count} values of {bits} bits")
    if bits in _WHOLE_BYTES:
        return np.frombuffer(data, dtype=_WHOLE_BYTES[bits], count=count).astype(np.uint64)
    buf = np.frombuffer(bytes(data) + bytes(8), dtype=np.uint8)
    start = np.arange(count, dtype=np.int64) * bits
    windows = np.lib.stride_tricks.sliding_window_view(buf, 8)[start >> 3]
    words = np.ascontiguousarray(windows).view(">u8").ravel().astype(np.uint64)
    return (words << (start & 7).astype(np.uint64)) >> np.uint64(64 - bits)
