"""Synthetic phone-photo-like pages of handwritten work (for evaluation and demo samples).

Lines are written with human glyph strokes (MathWriting) by a random Writer, on paper with
ruled lines, then rotated, unevenly lit, blurred and JPEG-compressed.
Returns the image bytes and ground-truth line boxes.
"""
from __future__ import annotations

import io
import math
import random
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from redpen.adapters.ink import Writer, smooth
from redpen.domain.model import LineBox

INKS = [(25, 30, 90), (20, 20, 25), (60, 60, 70), (15, 40, 120)]


def _rot(p, c, ang):
    s, co = math.sin(ang), math.cos(ang)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * co - y * s, c[1] + x * s + y * co)


def render_page(lines: List[str], seed: int, hard: bool = False) -> Tuple[bytes, List[LineBox]]:
    rng = random.Random(seed)
    writer = Writer(seed * 7 + 1)
    W = rng.choice([900, 1000, 1100])
    cap = rng.uniform(34, 52)
    pitch = cap * rng.uniform(2.0, 2.6)
    top = rng.uniform(90, 160)
    H = int(top + pitch * (len(lines) + 1.5))
    H = max(H, 700)
    paper = tuple(int(v) for v in (rng.uniform(232, 252), rng.uniform(230, 250), rng.uniform(215, 240)))
    S = 2
    img = Image.new("RGB", (W * S, H * S), paper)
    d = ImageDraw.Draw(img)
    ruled = rng.random() < 0.7
    rule_pitch = pitch
    if ruled:
        rule_col = (170, 190, 220) if rng.random() < 0.8 else (200, 200, 200)
        y = top + 0.15 * cap
        while y < H:
            d.line([(0, y * S), (W * S, y * S)], fill=rule_col, width=max(1, int(1.2 * S)))
            y += rule_pitch
        if rng.random() < 0.5:
            d.line([(110 * S, 0), (110 * S, H * S)], fill=(225, 150, 150), width=2 * S)
    ang = math.radians(rng.uniform(-3.0, 3.0) if not hard else rng.uniform(-6, 6))
    centre = (W / 2, H / 2)
    ink = rng.choice(INKS)
    pen = max(2.0, cap * rng.uniform(0.06, 0.09))
    boxes: List[LineBox] = []
    x0 = rng.uniform(140, 220)
    for i, text in enumerate(lines):
        base = top + pitch * i + rng.uniform(-0.08, 0.08) * cap
        indent = x0 + rng.uniform(-15, 25)
        strokes, _ = writer.layout(text, indent, base, cap)
        pts_all = []
        for s in strokes:
            sm = [_rot(p, centre, ang) for p in smooth(s)]
            pts_all += sm
            if len(sm) > 1:
                d.line([(x * S, y * S) for x, y in sm], fill=ink, width=int(pen * S), joint="curve")
        xs = [p[0] for p in pts_all]
        ys = [p[1] for p in pts_all]
        boxes.append(LineBox(int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))))
    img = img.resize((W, H), Image.LANCZOS)
    # uneven lighting / shadow
    a = np.asarray(img, dtype=np.float32)
    gx = np.linspace(0, 1, W)[None, :, None]
    gy = np.linspace(0, 1, H)[:, None, None]
    k = rng.uniform(0.0, 0.22 if not hard else 0.35)
    shade = 1 - k * (rng.random() * gx + rng.random() * gy)
    a = a * shade
    a += np.random.default_rng(seed).normal(0, rng.uniform(1.5, 5), a.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if rng.random() < 0.6:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.1)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=rng.randint(62, 88))
    return buf.getvalue(), boxes
