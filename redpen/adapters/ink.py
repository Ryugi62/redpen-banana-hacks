"""Handwriting from real human strokes.

Glyphs come from Google MathWriting `symbols/` (CC BY-NC-SA 4.0): each character is a
human-written ink sample. A `Writer` picks one sample per character (its "hand"),
then lays text out with per-glyph jitter, slant and baseline wobble.
"""
from __future__ import annotations

import json
import math
import os
import random
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

Point = Tuple[float, float]
Stroke = List[Point]

_DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "glyphs.json")

# (height, bottom) relative to cap height 1.0 with baseline at 0 (y grows upward here)
_CAP = (1.0, 0.0)
_X = (0.6, 0.0)
_DESC = (0.92, -0.32)
_METRICS: Dict[str, Tuple[float, float]] = {}
for c in "0123456789bdfhklt?!ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _METRICS[c] = _CAP
for c in "acemnorsuvwxz":
    _METRICS[c] = _X
for c in "gpqy":
    _METRICS[c] = _DESC
_METRICS.update({
    "i": (0.86, 0.0), "j": (1.15, -0.32), "+": (0.55, 0.12), "=": (0.36, 0.2), "-": (0.06, 0.37),
    "*": (0.22, 0.3), "(": (1.25, -0.15), ")": (1.25, -0.15), "/": (1.1, -0.05), ".": (0.1, 0.0),
    ",": (0.26, -0.16), "±": (0.7, 0.05), "√": (1.15, -0.05), "<": (0.6, 0.1), ">": (0.6, 0.1),
})
_FLAT_WIDTH = {"-": 0.5}


@lru_cache(maxsize=1)
def glyph_bank() -> Dict[str, list]:
    with open(os.path.normpath(_DATA), encoding="utf-8") as f:
        return json.load(f)["glyphs"]


class Writer:
    """One consistent 'hand'."""

    def __init__(self, seed: int, slant: float | None = None):
        self.rng = random.Random(seed)
        bank = glyph_bank()
        self.choice = {c: self.rng.randrange(len(v)) for c, v in bank.items()}
        self.slant = self.rng.uniform(0.05, 0.22) if slant is None else slant
        self.gap = self.rng.uniform(0.1, 0.18)
        self.wobble = self.rng.uniform(0.015, 0.045)

    def _glyph(self, ch: str):
        bank = glyph_bank()
        key = ch if ch in bank else ch.lower() if ch.lower() in bank else None
        if key is None:
            return None, None
        return key, bank[key][self.choice[key]]

    def layout(self, text: str, x: float, baseline: float, cap_px: float) -> Tuple[List[Stroke], Tuple[float, float, float, float]]:
        """Return strokes in image pixel coords (y down) and their bbox (x0, y0, x1, y1)."""
        strokes: List[Stroke] = []
        cur = x
        sup = False
        i = 0
        minx = miny = float("inf")
        maxx = maxy = float("-inf")
        while i < len(text):
            ch = text[i]
            if ch == "^":
                sup = True
                i += 1
                continue
            if ch == " ":
                cur += 0.42 * cap_px
                sup = False
                i += 1
                continue
            key, g = self._glyph(ch)
            if g is None:
                cur += 0.5 * cap_px
                i += 1
                continue
            scale_mul = 0.62 if sup else 1.0
            lift = 0.42 if sup else 0.0
            h_rel, bottom = _METRICS.get(key, _CAP)
            jitter = 1 + self.rng.uniform(-0.07, 0.07)
            size = cap_px * scale_mul * jitter
            gw, gh = g["w"], g["h"]
            if key in _FLAT_WIDTH or gh < 0.2 * max(gw, 1e-6) and key in "-=":
                sx = _FLAT_WIDTH.get(key, 0.5) * size / max(gw, 1e-6)
                sy = sx
            else:
                sy = h_rel * size / max(gh, 1e-6)
                sx = sy
            width = gw * sx
            base = baseline - bottom * cap_px * scale_mul - lift * cap_px - self.rng.uniform(-1, 1) * self.wobble * cap_px
            top = base - gh * sy
            for s in g["s"]:
                pts = []
                for px, py in s:
                    yy = top + py * sy
                    xx = cur + px * sx + (base - yy) * self.slant
                    pts.append((xx, yy))
                    minx, maxx = min(minx, xx), max(maxx, xx)
                    miny, maxy = min(miny, yy), max(maxy, yy)
                strokes.append(pts)
            cur += width + self.gap * cap_px * scale_mul
            if sup and (i + 1 >= len(text) or not text[i + 1].isdigit()):
                sup = False
            i += 1
        if not strokes:
            return [], (x, baseline - cap_px, x, baseline)
        return strokes, (minx, miny, maxx, maxy)

    def width_of(self, text: str, cap_px: float) -> float:
        state = self.rng.getstate()
        _, (x0, _, x1, _) = self.layout(text, 0, 0, cap_px)
        self.rng.setstate(state)
        return x1 - x0


def smooth(stroke: Sequence[Point], steps: int = 4) -> Stroke:
    """Catmull-Rom smoothing so simplified strokes look like ink, not polygons."""
    if len(stroke) < 3:
        return list(stroke)
    pts = [stroke[0]] + list(stroke) + [stroke[-1]]
    out: Stroke = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for t in range(steps):
            u = t / steps
            u2, u3 = u * u, u * u * u
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * u + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * u2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * u3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * u + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * u2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * u3)
            out.append((x, y))
    out.append(stroke[-1])
    return out


def wobbly_ellipse(cx: float, cy: float, rx: float, ry: float, rng: random.Random) -> Stroke:
    start = rng.uniform(0, 2 * math.pi)
    turns = rng.uniform(1.08, 1.2)
    n = 90
    pts = []
    for k in range(n + 1):
        t = start + 2 * math.pi * turns * k / n
        grow = 1 + 0.06 * (k / n) + 0.025 * math.sin(3 * t + start)
        pts.append((cx + rx * grow * math.cos(t), cy + ry * grow * math.sin(t)))
    return pts


def tick(x: float, y: float, size: float, rng: random.Random) -> List[Stroke]:
    a = (x, y - 0.35 * size)
    b = (x + 0.32 * size + rng.uniform(-2, 2), y + rng.uniform(-2, 2))
    c = (x + size * rng.uniform(0.95, 1.1), y - size * rng.uniform(0.95, 1.15))
    mid1 = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.04 * size)
    mid2 = ((b[0] + c[0]) / 2 - 0.05 * size, (b[1] + c[1]) / 2)
    return [smooth([a, mid1, b, mid2, c])]
