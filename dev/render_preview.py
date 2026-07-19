#!/usr/bin/env python3
"""Decode every configured parameter from a sample GRIB file and render PNGs.

No Home Assistant needed. Run:

    python3 dev/render_preview.py <path-to-grib-file> [output-dir]

Use dev/verify_knmi_source.py or the KNMI Open Data API directly to obtain a
sample file first (one HARMONIE tar member = one lead time, ~14MB).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components"))

from grib_overlay import grib_decode, render  # noqa: E402
from grib_overlay.sources.knmi import KNOWN_DATASETS  # noqa: E402


def main(grib_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = KNOWN_DATASETS[0]

    print(f"Dataset: {dataset.key}, {len(dataset.parameters)} parameters\n")

    for parameter in dataset.parameters:
        try:
            field = grib_decode.decode_parameter(grib_path, parameter)
        except grib_decode.GribDecodeError as err:
            print(f"[SKIP] {parameter.key}: {err}")
            continue

        frame, legend = render.render_field(
            field, colormap=parameter.colormap, value_range=parameter.value_range
        )

        png_path = out_dir / f"{parameter.key}.png"
        png_path.write_bytes(frame.png_bytes)

        print(
            f"[OK] {parameter.key:16s} valid_time={field.valid_time} run_time={field.run_time} "
            f"unit={field.unit} range=({legend.min_value:.2f}, {legend.max_value:.2f}) "
            f"bounds={frame.bounds} size={frame.width}x{frame.height} -> {png_path}"
        )

        meta_path = out_dir / f"{parameter.key}.json"
        meta_path.write_text(
            json.dumps(
                {
                    "parameter": parameter.key,
                    "valid_time": field.valid_time.isoformat(),
                    "run_time": field.run_time.isoformat(),
                    "unit": field.unit,
                    "bounds": frame.bounds,
                    "legend": {
                        "unit": legend.unit,
                        "min_value": legend.min_value,
                        "max_value": legend.max_value,
                        "stops": legend.stops,
                    },
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    grib_file = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else REPO_ROOT / "dev" / "output"
    main(grib_file, output_dir)
