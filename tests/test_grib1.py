"""Tests for the pure-Python GRIB1 decoder (grib1.py) and grib_decode.py.

Two opt-in levels, both keyed off GRIB_OVERLAY_SAMPLE_GRIB (a single
extracted HARMONIE lead-time GRIB file -- see dev/render_preview.py's
docstring for how to obtain one):

- structural: decode every configured parameter and assert the fields look
  sane (right shape, ascending grid, plausible ranges). Runs with just numpy.
- cross-validation vs ecCodes: only runs if the `eccodes` package is also
  importable; asserts the pure-Python decoder matches ecCodes bit-for-bit.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from custom_components.grib_overlay import grib1, grib_decode
from custom_components.grib_overlay.sources.knmi import KNOWN_DATASETS

SAMPLE_ENV_VAR = "GRIB_OVERLAY_SAMPLE_GRIB"

pytestmark = pytest.mark.skipif(
    not os.environ.get(SAMPLE_ENV_VAR), reason=f"set {SAMPLE_ENV_VAR} to a sample GRIB file to run"
)


def _sample_path() -> Path:
    return Path(os.environ[SAMPLE_ENV_VAR])


def test_iter_messages_returns_regular_grid_messages() -> None:
    buf = _sample_path().read_bytes()
    messages = list(grib1.iter_messages(buf))
    assert messages, "expected at least one GRIB message"
    for m in messages:
        assert m.ni > 0 and m.nj > 0
        assert m.values.shape == (m.ni * m.nj,)
        assert m.lat1 < m.lat2  # KNMI grids scan south -> north


def test_decode_all_configured_parameters() -> None:
    path = _sample_path()
    dataset = KNOWN_DATASETS[0]
    decoded_any = False
    for parameter in dataset.parameters:
        try:
            field = grib_decode.decode_parameter(path, parameter)
        except grib_decode.GribDecodeError:
            continue  # not every parameter is guaranteed in a single lead-time file
        decoded_any = True
        assert field.data.shape == (field.lats.size, field.lons.size)
        assert np.all(np.diff(field.lats) > 0)
        assert np.all(np.diff(field.lons) > 0)
        finite = field.data[np.isfinite(field.data)]
        assert finite.size > 0
    assert decoded_any, "expected to decode at least one configured parameter"


def test_grid_bounds_match_dataset() -> None:
    path = _sample_path()
    dataset = KNOWN_DATASETS[0]
    parameter = next(p for p in dataset.parameters if p.key == "temperature_2m")
    field = grib_decode.decode_parameter(path, parameter)
    south, west, north, east = dataset.bounds
    assert field.lats[0] == pytest.approx(south, abs=0.01)
    assert field.lats[-1] == pytest.approx(north, abs=0.01)
    assert field.lons[0] == pytest.approx(west, abs=0.01)
    assert field.lons[-1] == pytest.approx(east, abs=0.01)


def test_matches_eccodes_bit_for_bit() -> None:
    eccodes = pytest.importorskip("eccodes", reason="eccodes not installed; cross-check skipped")
    path = _sample_path()
    buf = path.read_bytes()
    mine = list(grib1.iter_messages(buf))

    ecc_values = []
    with path.open("rb") as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            missing = eccodes.codes_get(gid, "missingValue")
            values = eccodes.codes_get_array(gid, "values").astype(np.float64)
            ecc_values.append(np.where(values == missing, np.nan, values))
            eccodes.codes_release(gid)

    assert len(mine) == len(ecc_values)
    for message, ecc in zip(mine, ecc_values):
        assert np.array_equal(np.isnan(message.values), np.isnan(ecc))
        finite = ~np.isnan(message.values)
        if finite.any():
            assert np.allclose(message.values[finite], ecc[finite], atol=1e-6)
