"""Upright detection for photos taken sideways without EXIF (common with notebook photos).

Text lines make the row profile of the ink mask spiky. If the column profile is clearly
spikier, the page is sideways; the rotation direction is chosen so that line starts are
clockwise (see note in upright()).
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from .imageio import load_rgb
from .segmenter import ProjectionSegmenter


def _spikiness(prof: np.ndarray) -> float:
    nz = np.where(prof > 0)[0]
    if len(nz) < 2:
        return 0.0
    p = prof[nz[0]: nz[-1] + 1]
    return float(np.std(p) / (np.mean(p) + 1e-9))


def _start_end_spread(mask: np.ndarray, seg: ProjectionSegmenter) -> float:
    starts, ends = [], []
    for a, b in seg._bands(mask):
        cols = np.where(mask[a:b].sum(axis=0) > 0)[0]
        if len(cols):
            starts.append(cols[0])
            ends.append(cols[-1])
    if len(starts) < 2:
        return 0.0
    return float(np.std(ends) - np.std(starts))  # positive = starts aligned (upright)


def upright(img: Image.Image) -> Image.Image:
    seg = ProjectionSegmenter()
    small = img.copy()
    small.thumbnail((700, 700))
    mask = seg.ink_mask(small)
    rows = _spikiness(mask.sum(axis=1).astype(float))
    cols = _spikiness(mask.sum(axis=0).astype(float))
    if cols <= rows * 1.35:
        return img
    # Direction: phone photos that lost their EXIF tag are almost always turned 90 deg
    # counter-clockwise (4/4 on the real answer sheets we tested; the line-alignment cue
    # was right only 2/4), so we turn clockwise. Photos with EXIF never reach this point.
    return img.transpose(Image.Transpose.ROTATE_270)  # PIL ROTATE_270 = 90 deg clockwise


def upright_bytes(data: bytes) -> bytes:
    img = upright(load_rgb(data))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
