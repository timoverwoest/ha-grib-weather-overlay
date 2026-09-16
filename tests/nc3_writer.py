"""A tiny NetCDF-3 (classic) writer for tests -- just enough for Matroos-like files."""

from __future__ import annotations

import struct

import numpy as np

_TYPE = {np.dtype(">i2"): 3, np.dtype(">i4"): 4, np.dtype(">f4"): 5, np.dtype(">f8"): 6}


def _pad(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def _name(s: str) -> bytes:
    raw = s.encode()
    return struct.pack(">I", len(raw)) + _pad(raw)


def _attrs(attrs: dict) -> bytes:
    if not attrs:
        return b"\0" * 8
    out = struct.pack(">II", 0x0C, len(attrs))
    for key, value in attrs.items():
        out += _name(key)
        if isinstance(value, str):
            raw = value.encode()
            out += struct.pack(">II", 2, len(raw)) + _pad(raw)
        else:
            arr = np.atleast_1d(np.asarray(value)).astype(">f4")
            out += struct.pack(">II", 5, arr.size) + _pad(arr.tobytes())
    return out


def write(dims: list[tuple[str, int | None]], variables: list[tuple[str, list[str], np.ndarray, dict]],
          global_attrs: dict | None = None, numrecs: int = 0) -> bytes:
    """``dims``: (name, length or None for the record dimension).
    ``variables``: (name, dim names, data in dimension order, attributes)."""
    dim_index = {n: i for i, (n, _) in enumerate(dims)}
    record_dim = next((n for n, length in dims if length is None), None)
    header = b"CDF\x01" + struct.pack(">I", numrecs)
    header += struct.pack(">II", 0x0A, len(dims))
    for n, length in dims:
        header += _name(n) + struct.pack(">I", length or 0)
    header += _attrs(global_attrs or {})

    prepared = []
    for n, vdims, data, attrs in variables:
        arr = np.asarray(data)
        arr = arr.astype(arr.dtype.newbyteorder(">"))
        is_rec = bool(vdims) and vdims[0] == record_dim
        # Slices, not arr[r]: a numpy scalar forgets its byte order.
        per_record = arr[0:1].tobytes() if is_rec else None
        prepared.append((n, vdims, arr, attrs, is_rec, len(_pad(per_record)) if is_rec else len(_pad(arr.tobytes()))))

    def var_header(begins: list[int]) -> bytes:
        out = struct.pack(">II", 0x0B, len(prepared))
        for (n, vdims, arr, attrs, is_rec, vsize), begin in zip(prepared, begins):
            out += _name(n) + struct.pack(">I", len(vdims))
            out += b"".join(struct.pack(">I", dim_index[d]) for d in vdims)
            out += _attrs(attrs) + struct.pack(">III", _TYPE[arr.dtype], vsize, begin)
        return out

    size = len(header) + len(var_header([0] * len(prepared)))
    begins, body_fixed, cursor = [], b"", size
    for n, vdims, arr, attrs, is_rec, vsize in prepared:
        if not is_rec:
            begins.append(cursor)
            chunk = _pad(arr.tobytes())
            body_fixed += chunk
            cursor += len(chunk)
        else:
            begins.append(None)
    rec_vars = [p for p in prepared if p[4]]
    single = len(rec_vars) == 1
    offset = 0
    for i, p in enumerate(prepared):
        if p[4]:
            begins[i] = cursor + offset
            offset += p[5]
    body_rec = b""
    for r in range(numrecs):
        for p in rec_vars:
            raw = p[2][r:r + 1].tobytes()
            body_rec += raw if single else _pad(raw)
    return header + var_header(begins) + body_fixed + body_rec
