#!/usr/bin/env python3
"""Generate the integration brand icon (sea-chart / waves / wind theme).

Renders at high resolution and downscales for crisp anti-aliasing, writing
custom_components/grib_overlay/brand/icon.png (256x256) and icon@2x.png
(512x512). Requires only Pillow.

    python3 dev/make_brand_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SS = 1024  # supersample resolution
BRAND_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "grib_overlay" / "brand"


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def _rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _vertical_gradient(size, top, bottom):
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        c = _lerp(top, bottom, y / (size - 1))
        for x in range(size):
            px[x, y] = c
    return grad


def _wave_ribbon(draw, size, y_base, amp, thickness, wl, phase, color, n=600):
    top, bot = [], []
    for i in range(n + 1):
        x = size * i / n
        y = y_base + amp * math.sin((x / wl) * 2 * math.pi + phase)
        top.append((x, y))
        bot.append((x, y + thickness))
    draw.polygon(top + bot[::-1], fill=color)


def _stamp_stroke(base_rgba, pts, radius, color):
    # Round-capped stroke via circles stamped on a separate layer, composited
    # once so overlapping stamps don't accumulate opacity.
    layer = Image.new("RGBA", base_rgba.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x, y in pts:
        d.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)
    base_rgba.alpha_composite(layer)


def _wind_path(size, x0, x1, y, sway, curl_r, curl_sweep_deg=300, n=220, m=140):
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((x0 + (x1 - x0) * t, y + sway * math.sin(t * math.pi)))
    cx, cy = x1, y - curl_r
    start = math.pi / 2
    sweep = math.radians(curl_sweep_deg)
    for i in range(m + 1):
        ang = start + sweep * (i / m)
        pts.append((cx + curl_r * math.cos(ang), cy + curl_r * math.sin(ang)))
    return pts


def build(size):
    radius = int(size * 0.225)
    mask = _rounded_mask(size, radius)
    badge = _vertical_gradient(size, (60, 150, 202), (9, 38, 71)).convert("RGBA")
    badge.putalpha(mask)
    draw = ImageDraw.Draw(badge, "RGBA")

    # sea-chart graticule
    step = size // 7
    gw = max(1, size // 400)
    for gx in range(step, size, step):
        draw.line([(gx, 0), (gx, size)], fill=(255, 255, 255, 20), width=gw)
    for gy in range(step, size, step):
        draw.line([(0, gy), (size, gy)], fill=(255, 255, 255, 20), width=gw)

    # wind streaks above the waves
    wr = size * 0.026
    _stamp_stroke(badge, _wind_path(size, size * 0.12, size * 0.60, size * 0.30, size * 0.02, size * 0.075), wr, (255, 255, 255, 205))
    _stamp_stroke(badge, _wind_path(size, size * 0.18, size * 0.66, size * 0.44, size * 0.02, size * 0.062), wr * 0.9, (255, 255, 255, 175))

    draw = ImageDraw.Draw(badge, "RGBA")
    wl = size * 0.66
    for y_base, amp, thick, phase, color in [
        (size * 0.88, size * 0.042, size * 0.058, 2.2, (128, 182, 220, 235)),
        (size * 0.75, size * 0.048, size * 0.064, 1.1, (196, 227, 246, 240)),
        (size * 0.63, size * 0.052, size * 0.070, 0.0, (255, 255, 255, 245)),
    ]:
        _wave_ribbon(draw, size, y_base, amp, thick, wl, phase, color)

    r, g, b, a = badge.split()
    a = Image.composite(a, Image.new("L", badge.size, 0), mask)
    return Image.merge("RGBA", (r, g, b, a))


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    hi = build(SS)
    for name, target in [("icon.png", 256), ("icon@2x.png", 512)]:
        hi.resize((target, target), Image.LANCZOS).save(BRAND_DIR / name, optimize=True)
        print("wrote", BRAND_DIR / name)


if __name__ == "__main__":
    main()
