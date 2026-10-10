"""AC-9: red ink lands around the slip, never over other lines' interiors."""
import io

import numpy as np
from PIL import Image, ImageDraw

from redpen.adapters.renderer import InkRenderer
from redpen.domain.markup import plan_markup
from redpen.domain.model import LineBox, Step
from redpen.domain.verdict import judge


def page_bytes(w=900, h=420):
    img = Image.new("RGB", (w, h), (250, 248, 240))
    d = ImageDraw.Draw(img)
    for i in range(3):
        d.rectangle([40, 40 + 120 * i, 420, 100 + 120 * i], outline=(30, 30, 30), width=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def red_mask(img):
    a = np.asarray(img.convert("RGB")).astype(int)
    return (a[..., 0] > 150) & (a[..., 1] < 110) & (a[..., 2] < 120)


def test_slip_is_circled_and_other_lines_stay_clean():
    boxes = [LineBox(40, 40 + 120 * i, 420, 100 + 120 * i) for i in range(3)]
    steps = [Step(i, t, 0.99, boxes[i]) for i, t in enumerate(["2x+3=7", "2x=10", "x=5"])]
    plan = plan_markup(steps, judge(steps))
    out = InkRenderer().render_image(page_bytes(), steps, plan)
    assert out.height == 420 and out.width >= 900
    red = red_mask(out)
    b = boxes[1]
    ring = red[max(0, b.y0 - 40):b.y1 + 40, max(0, b.x0 - 60):b.x1 + 260]
    assert ring.sum() > 200  # circle + note present near the slip
    for other in (boxes[0], boxes[2]):
        inner = red[other.y0 + 8:other.y1 - 8, other.x0 + 8:other.x1 - 8]
        assert inner.sum() == 0


def test_margin_added_when_no_room():
    boxes = [LineBox(20, 40, 880, 100), LineBox(20, 160, 880, 220)]
    steps = [Step(0, "2x=4", 0.99, boxes[0]), Step(1, "x=3", 0.99, boxes[1])]
    out = InkRenderer().render_image(page_bytes(), steps, plan_markup(steps, judge(steps)))
    assert out.width > 900
