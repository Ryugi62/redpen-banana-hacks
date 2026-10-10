"""ProjectionSegmenter: classical CV line finding (no model).

background division -> ink mask -> ruled-line removal -> deskew search -> horizontal
projection bands -> merge superscripts/fractions -> line boxes in page pixels.
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageFilter

from redpen.domain.model import LineBox

from .imageio import load_rgb


def _runs_mask(mask: np.ndarray, k: int, axis: int) -> np.ndarray:
    """Pixels that belong to a run of >= k consecutive ink pixels along axis."""
    m = mask if axis == 1 else mask.T
    h, w = m.shape
    if k >= w:
        return np.zeros_like(mask)
    c = np.cumsum(np.pad(m.astype(np.int32), ((0, 0), (1, 0))), axis=1)
    rows, cols = np.where((c[:, k:] - c[:, :-k]) == k)  # window [j, j+k) all ink
    marks = np.zeros((h, w + 1), dtype=np.int32)
    np.add.at(marks, (rows, cols), 1)
    np.add.at(marks, (rows, np.minimum(cols + k, w)), -1)
    res = (np.cumsum(marks[:, :w], axis=1) > 0) & m
    return res if axis == 1 else res.T


class ProjectionSegmenter:
    def __init__(self, work_width: int = 900):
        self.work_width = work_width

    def ink_mask(self, img: Image.Image) -> np.ndarray:
        g = img.convert("L")
        bg = g.filter(ImageFilter.GaussianBlur(radius=max(8, g.width // 40)))
        a = np.asarray(g, dtype=np.float32)
        b = np.asarray(bg, dtype=np.float32) + 1.0
        ratio = a / b
        mask = ratio < 0.78
        # remove ruled lines and margins: long thin horizontal / vertical runs
        h, w = mask.shape
        horiz = _runs_mask(mask, max(30, int(w * 0.18)), axis=1)
        vert = _runs_mask(mask, max(30, int(h * 0.3)), axis=0)
        mask = mask & ~horiz & ~vert
        return mask

    def _best_angle(self, mask: np.ndarray) -> float:
        best, best_score = 0.0, -1.0
        im = Image.fromarray((mask * 255).astype(np.uint8))
        for deg in np.arange(-6, 6.01, 1.0):
            r = np.asarray(im.rotate(deg, resample=Image.NEAREST, expand=False)) > 0
            prof = r.sum(axis=1).astype(np.float64)
            score = float(np.var(prof))
            if score > best_score:
                best, best_score = float(deg), score
        # refine
        for deg in np.arange(best - 0.75, best + 0.76, 0.25):
            r = np.asarray(im.rotate(deg, resample=Image.NEAREST, expand=False)) > 0
            score = float(np.var(r.sum(axis=1).astype(np.float64)))
            if score > best_score:
                best, best_score = float(deg), score
        return best

    def _bands(self, mask: np.ndarray) -> List[Tuple[int, int]]:
        h, w = mask.shape
        prof = mask.sum(axis=1).astype(np.float64)
        kernel = np.ones(3) / 3
        prof = np.convolve(prof, kernel, mode="same")
        thr = max(2.0, 0.004 * w)
        on = prof > thr
        bands, start = [], None
        for y, v in enumerate(on):
            if v and start is None:
                start = y
            elif not v and start is not None:
                bands.append((start, y))
                start = None
        if start is not None:
            bands.append((start, h))
        if not bands:
            return []
        heights = sorted(b - a for a, b in bands)
        med = heights[len(heights) // 2]
        # merge bands separated by small gaps (superscripts, fraction bars, dots of i/j)
        merged = [bands[0]]
        for a, b in bands[1:]:
            pa, pb = merged[-1]
            gap = a - pb
            small = (b - a) < 0.45 * med or (pb - pa) < 0.45 * med
            if gap < 0.22 * med or (small and gap < 0.6 * med):
                merged[-1] = (pa, b)
            else:
                merged.append((a, b))
        heights = sorted(b - a for a, b in merged)
        med = heights[len(heights) // 2]
        return [(a, b) for a, b in merged if (b - a) >= 0.35 * med and mask[a:b].sum() > 0.15 * med * med]

    def page_size(self, image: bytes):
        return load_rgb(image).size

    def segment(self, image: bytes) -> List[LineBox]:
        img = load_rgb(image)
        W, H = img.size
        k = self.work_width / W if W > self.work_width else 1.0
        small = img.resize((int(W * k), int(H * k)), Image.LANCZOS) if k < 1 else img
        mask = self.ink_mask(small)
        ang = self._best_angle(mask)
        im = Image.fromarray((mask * 255).astype(np.uint8))
        rot = np.asarray(im.rotate(ang, resample=Image.NEAREST, expand=False)) > 0
        boxes: List[LineBox] = []
        h, w = rot.shape
        cx, cy = w / 2, h / 2
        rad = math.radians(ang)  # PIL rotates counter-clockwise; map back clockwise
        for a, b in self._bands(rot):
            cols = rot[a:b].sum(axis=0)
            xs = np.where(cols > 0)[0]
            if len(xs) == 0:
                continue
            # trim isolated specks at the ends
            x0, x1 = int(xs[0]), int(xs[-1])
            corners = [(x0, a), (x1, a), (x0, b), (x1, b)]
            back = []
            for x, y in corners:
                dx, dy = x - cx, y - cy
                bx = cx + dx * math.cos(rad) - dy * math.sin(rad)
                by = cy + dx * math.sin(rad) + dy * math.cos(rad)
                back.append((bx / k, by / k))
            bx0 = max(0, int(min(p[0] for p in back)))
            by0 = max(0, int(min(p[1] for p in back)))
            bx1 = min(W, int(max(p[0] for p in back)) + 1)
            by1 = min(H, int(max(p[1] for p in back)) + 1)
            boxes.append(LineBox(bx0, by0, bx1, by1))
        return boxes
