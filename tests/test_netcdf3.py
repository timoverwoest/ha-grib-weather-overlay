"""The pure-numpy NetCDF-3 reader used for Rijkswaterstaat's Matroos output."""

from __future__ import annotations

import numpy as np
import pytest

from custom_components.grib_overlay import netcdf3
from tests import nc3_writer


def _matroos_like(times=3, fill=-9999.0) -> tuple[bytes, np.ndarray]:
    sep = np.arange(times * 2 * 3, dtype=">f4").reshape(times, 2, 3)
    sep[0, 0, 0] = fill
    velu = -sep
    buf = nc3_writer.write(
        dims=[("time", None), ("y", 2), ("x", 3)],
        variables=[
            ("x", ["x"], np.array([4.0, 4.05, 4.1], ">f8"), {"units": "degrees_east"}),
            ("y", ["y"], np.array([52.0, 52.05], ">f8"), {"units": "degrees_north"}),
            ("time", ["time"], np.array([0.0, 60.0, 120.0][:times], ">f8"), {"units": "minutes since 1970-01-01"}),
            ("sep", ["time", "y", "x"], sep, {"_FillValue": fill, "units": "m"}),
            ("velu", ["time", "y", "x"], velu, {"_FillValue": fill}),
        ],
        global_attrs={"analysis_time": "1970-01-01 00:00:00 GMT"},
        numrecs=times,
    )
    return buf, sep


def test_reads_record_variables_and_fill_values() -> None:
    buf, sep = _matroos_like()
    data = netcdf3.read(buf)
    assert data.dimensions == {"time": 3, "y": 2, "x": 3}
    assert data.attributes["analysis_time"].startswith("1970")
    assert data.variables["x"].data.tolist() == [4.0, 4.05, 4.1]
    got = data.variables["sep"].masked()
    assert got.shape == (3, 2, 3)
    assert np.isnan(got[0, 0, 0])
    assert got[2, 1, 2] == sep[2, 1, 2]
    assert np.array_equal(data.variables["velu"].masked()[1:], -sep[1:])


def test_single_record_variable_has_no_padding() -> None:
    odd = np.array([[1, 2, 3]], ">i2")  # 6 bytes per record: unpadded when alone
    buf = nc3_writer.write(
        dims=[("time", None), ("x", 3)],
        variables=[("v", ["time", "x"], np.vstack([odd, odd + 10]), {})],
        numrecs=2,
    )
    assert netcdf3.read(buf).variables["v"].data.tolist() == [[1, 2, 3], [11, 12, 13]]


def test_refuses_other_formats() -> None:
    with pytest.raises(netcdf3.NetCDFError, match="HDF5"):
        netcdf3.read(b"\x89HDF\r\n\x1a\n" + b"\0" * 20)
    with pytest.raises(netcdf3.NetCDFError):
        netcdf3.read(b"ERROR in matroos.pl: fout")


def test_truncated_file_is_an_error() -> None:
    buf, _ = _matroos_like()
    with pytest.raises(netcdf3.NetCDFError, match="truncated"):
        netcdf3.read(buf[:-10])
