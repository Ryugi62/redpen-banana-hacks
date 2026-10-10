"""InkRenderer: draws the MarkupPlan onto the student's own photo as red-pen ink.

Notes are written in handwriting assembled from real human glyph strokes (MathWriting).
If there is no room to the right of the work, a paper-coloured margin is added so the
red pen never writes over the student's lines.
"""
from __future__ import annotations

import random
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from redpen.domain.model import LineBox, MarkKind, MarkupPlan, Step

from .imageio import load_rgb, to_png
from .ink import Stroke, Writer, smooth, tick, wobbly_ellipse

INK = (206, 22, 38)
SS = 2  # supersampling factor for anti-aliased ink


def _paper_colour(img: Image.Image) -> Tuple[int, int, int]:
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = a.shape
    strip = a[:, max(0, w - max(4, w // 40)):, :].reshape(-1, 3)
    return tuple(int(v) for v in np.percentile(strip, 75, axis=0))


class InkRenderer:
    def __init__(self, seed: int = 11, note_writer_seed: int = 3):  # writer 3: most legible of 8 compared on every hint note
        self.seed = seed
        self.note_writer_seed = note_writer_seed

    # ------------------------------------------------------------- layout
    def _plan_margin(self, img: Image.Image, steps: List[Step], plan: MarkupPlan, writer: Writer) -> int:
        w = img.width
        need = 0
        for m in plan.marks:
            if m.step is None or steps[m.step].box is None:
                continue
            box = steps[m.step].box
            cap = self._cap(box)
            if m.kind == MarkKind.NOTE:
                need = max(need, int(box.x1 + 0.6 * cap + writer.width_of(m.text, 0.55 * cap) + 1.3 * cap - w))
            elif m.kind in (MarkKind.TICK, MarkKind.QUERY):
                need = max(need, int(box.x1 + 1.6 * cap - w))
        return max(0, need)

    @staticmethod
    def _cap(box: LineBox) -> float:
        return max(14.0, min(80.0, box.height * 0.75))

    # ------------------------------------------------------------- render
    def render_image(self, image: bytes, steps: List[Step], plan: MarkupPlan) -> Image.Image:
        img = load_rgb(image)
        writer = Writer(self.note_writer_seed, slant=0.12)
        rng = random.Random(self.seed)
        margin = self._plan_margin(img, steps, plan, writer)
        if margin:
            canvas = Image.new("RGB", (img.width + margin, img.height), _paper_colour(img))
            canvas.paste(img, (0, 0))
            img = canvas
        layer = Image.new("L", (img.width * SS, img.height * SS), 0)
        d = ImageDraw.Draw(layer)
        boxes = [s.box for s in steps]

        def draw(strokes: List[Stroke], width: float):
            for s in strokes:
                pts = [(x * SS, y * SS) for x, y in s]
                if len(pts) == 1:
                    x, y = pts[0]
                    r = width * SS / 2
                    d.ellipse([x - r, y - r, x + r, y + r], fill=255)
                elif len(pts) > 1:
                    d.line(pts, fill=255, width=max(1, int(width * SS)), joint="curve")

        for m in plan.marks:
            box: Optional[LineBox] = boxes[m.step] if m.step is not None and m.step < len(boxes) else None
            if m.kind == MarkKind.SUMMARY:
                self._summary(m.text, boxes, img, writer, draw)
                continue
            if box is None:
                continue
            cap = self._cap(box)
            pen = max(2.0, cap * 0.085)
            if m.kind == MarkKind.TICK:
                draw(tick(box.x1 + 0.35 * cap, box.y0 + box.height * 0.62, 0.8 * cap, rng), pen)
            elif m.kind == MarkKind.QUERY:
                strokes, _ = writer.layout("?", box.x1 + 0.35 * cap, box.y1 - 0.15 * box.height, 0.9 * cap)
                draw([smooth(s) for s in strokes], pen)
            elif m.kind == MarkKind.CIRCLE:
                gap = self._vertical_room(box, boxes)
                rx = box.width / 2 + 0.25 * cap
                ry = box.height / 2 + min(0.3 * cap, gap)
                draw([smooth(wobbly_ellipse((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2, rx, ry, rng), 2)], pen * 1.1)
            elif m.kind == MarkKind.NOTE:
                ncap = 0.55 * cap
                x = box.x1 + 0.6 * cap
                base = box.y0 + box.height * 0.55
                strokes, (nx0, ny0, nx1, ny1) = writer.layout(m.text, x, base, ncap)
                draw([smooth(s) for s in strokes], max(1.6, pen * 0.75))
                # underline the note so it reads as a teacher's comment
                draw([smooth([(nx0, ny1 + 0.25 * ncap), ((nx0 + nx1) / 2, ny1 + 0.32 * ncap), (nx1, ny1 + 0.22 * ncap)])], max(1.4, pen * 0.6))
        ink = layer.resize(img.size, Image.LANCZOS)
        red = Image.new("RGB", img.size, INK)
        alpha = ink.point(lambda v: int(v * 0.9))
        img.paste(red, (0, 0), alpha)
        return img

    def render(self, image: bytes, steps: List[Step], plan: MarkupPlan) -> bytes:
        return to_png(self.render_image(image, steps, plan))

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _vertical_room(box: LineBox, boxes: List[Optional[LineBox]]) -> float:
        room = 1e9
        for b in boxes:
            if b is None or b == box:
                continue
            if b.y1 <= box.y0:
                room = min(room, (box.y0 - b.y1) / 2)
            elif b.y0 >= box.y1:
                room = min(room, (b.y0 - box.y1) / 2)
        return max(2.0, room if room < 1e9 else 40.0)

    def _summary(self, text: str, boxes: List[Optional[LineBox]], img: Image.Image, writer: Writer, draw) -> None:
        real = [b for b in boxes if b is not None]
        if not real:
            return
        last = max(real, key=lambda b: b.y1)
        cap = self._cap(last) * 0.7
        y = min(img.height - 0.3 * cap, last.y1 + 1.4 * cap)
        x = min(b.x0 for b in real)
        strokes, (x0, y0, x1, y1) = writer.layout(text, x, y, cap)
        pen = max(2.0, cap * 0.1)
        draw([smooth(s) for s in strokes], pen)
        draw([smooth([(x0, y1 + 0.3 * cap), (x1, y1 + 0.22 * cap)]), smooth([(x0 + 0.1 * cap, y1 + 0.52 * cap), (x1 - 0.1 * cap, y1 + 0.46 * cap)])], pen * 0.8)
