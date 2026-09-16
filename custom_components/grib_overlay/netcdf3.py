"""Minimal, dependency-free NetCDF-3 reader (classic and 64-bit offset).

Rijkswaterstaat's NOOS-Matroos serves its model output as NetCDF-3. The usual
readers (netCDF4, h5py, scipy) are compiled packages without a wheel for every
Home Assistant platform -- the same trap eccodes was for GRIB -- and NetCDF-3
is simple enough to read with numpy: a header, then big-endian arrays at known
offsets. NetCDF-4 (HDF5) is a different format and is refused.

Blocking by design; callers run it in an executor.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

_NC_DIMENSION = 0x0A
_NC_VARIABLE = 0x0B
_NC_ATTRIBUTE = 0x0C

# nc_type -> (numpy dtype, size in bytes)
_TYPES = {
    1: (">i1", 1),  # byte
    2: ("S1", 1),  # char
    3: (">i2", 2),  # short
    4: (">i4", 4),  # int
    5: (">f4", 4),  # float
    6: (">f8", 8),  # double
}


class NetCDFError(Exception):
    """Raised for anything that isn't a NetCDF-3 file this reader understands."""


@dataclass
class Variable:
    name: str
    dimensions: tuple[str, ...]
    attributes: dict = field(default_factory=dict)
    data: np.ndarray | None = None

    def masked(self) -> np.ndarray:
        """Data as float64 with ``_FillValue`` / ``missing_value`` as NaN, scale applied."""
        values = np.array(self.data, dtype=np.float64)
        for key in ("_FillValue", "missing_value"):
            fill = self.attributes.get(key)
            if fill is not None and len(fill):
                values[values == float(fill[0])] = np.nan
        scale = self.attributes.get("scale_factor")
        offset = self.attributes.get("add_offset")
        if scale is not None and len(scale):
            values = values * float(scale[0])
        if offset is not None and len(offset):
            values = values + float(offset[0])
        return values


@dataclass
class Dataset:
    dimensions: dict[str, int]
    attributes: dict
    variables: dict[str, Variable]


def read(buf: bytes) -> Dataset:
    """Parse a whole NetCDF-3 file held in memory."""
    if buf[:3] != b"CDF" or buf[3:4] not in (b"\x01", b"\x02"):
        if buf[:4] == b"\x89HDF":
            raise NetCDFError("NetCDF-4/HDF5 is not supported")
        raise NetCDFError("not a NetCDF-3 file")
    offset_size = 8 if buf[3] == 2 else 4
    pos = 4

    def u32() -> int:
        nonlocal pos
        (value,) = struct.unpack_from(">I", buf, pos)
        pos += 4
        return value

    def offset() -> int:
        nonlocal pos
        value = struct.unpack_from(">Q" if offset_size == 8 else ">I", buf, pos)[0]
        pos += offset_size
        return value

    def name() -> str:
        nonlocal pos
        length = u32()
        text = buf[pos:pos + length].decode("utf-8", errors="replace")
        pos += (length + 3) & ~3
        return text

    def header_list(expected_tag: int) -> int:
        tag, count = u32(), u32()
        if tag not in (0, expected_tag):
            raise NetCDFError(f"unexpected header tag {tag:#x}")
        return count if tag else 0

    def attributes() -> dict:
        nonlocal pos
        out = {}
        for _ in range(header_list(_NC_ATTRIBUTE)):
            key = name()
            nc_type, count = u32(), u32()
            if nc_type not in _TYPES:
                raise NetCDFError(f"unknown attribute type {nc_type}")
            dtype, size = _TYPES[nc_type]
            raw = buf[pos:pos + count * size]
            pos += (count * size + 3) & ~3
            out[key] = raw.decode("utf-8", errors="replace") if nc_type == 2 else np.frombuffer(raw, dtype)
        return out

    numrecs = u32()
    dims = [(name(), u32()) for _ in range(header_list(_NC_DIMENSION))]
    global_attributes = attributes()

    headers = []
    for _ in range(header_list(_NC_VARIABLE)):
        var_name = name()
        dim_ids = [u32() for _ in range(u32())]
        var_attributes = attributes()
        nc_type, vsize, begin = u32(), u32(), offset()
        if nc_type not in _TYPES:
            raise NetCDFError(f"unknown variable type {nc_type}")
        headers.append((var_name, dim_ids, var_attributes, nc_type, vsize, begin))

    # The record (unlimited, length 0) dimension, if any, is always the first
    # dimension of a record variable; record data is interleaved per record.
    def is_record(dim_ids: list[int]) -> bool:
        return bool(dim_ids) and dims[dim_ids[0]][1] == 0

    def unpadded(dim_ids: list[int], nc_type: int) -> int:
        return int(np.prod([dims[i][1] for i in dim_ids[1:]])) * _TYPES[nc_type][1]

    record_vars = [h for h in headers if is_record(h[1])]
    if len(record_vars) == 1:
        # A lone record variable is stored without the padding to 4 bytes
        # (its vsize in the header may still be the padded size).
        recsize = unpadded(record_vars[0][1], record_vars[0][3])
    else:
        recsize = sum(h[4] for h in record_vars)

    variables = {}
    for var_name, dim_ids, var_attributes, nc_type, vsize, begin in headers:
        dtype, size = _TYPES[nc_type]
        shape = [dims[i][1] for i in dim_ids]
        if is_record(dim_ids):
            per_record = int(np.prod(shape[1:])) if len(shape) > 1 else 1
            shape[0] = numrecs
            if begin + (numrecs - 1) * recsize + per_record * size > len(buf) and numrecs:
                raise NetCDFError(f"file truncated in variable {var_name}")
            data = np.stack(
                [np.frombuffer(buf, dtype, per_record, begin + r * recsize) for r in range(numrecs)]
            ) if numrecs else np.empty((0, per_record), dtype)
            data = data.reshape(shape)
        else:
            count = int(np.prod(shape)) if shape else 1
            if begin + count * size > len(buf):
                raise NetCDFError(f"file truncated in variable {var_name}")
            data = np.frombuffer(buf, dtype, count, begin).reshape(shape)
        variables[var_name] = Variable(
            name=var_name,
            dimensions=tuple(dims[i][0] for i in dim_ids),
            attributes=var_attributes,
            data=data,
        )
    return Dataset(
        dimensions={n: (numrecs if length == 0 else length) for n, length in dims},
        attributes=global_attributes,
        variables=variables,
    )
