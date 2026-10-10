import io

from PIL import Image

from eval.synth import render_page
from redpen.adapters.imageio import load_rgb
from redpen.adapters.orient import upright


def test_sideways_pages_are_turned_upright():
    ok = 0
    for seed in range(6):
        b, _ = render_page(["2x+3=7", "2x=4", "x=2", "x+1=3"], seed=300 + seed)
        img = load_rgb(b)
        for k in (Image.Transpose.ROTATE_90, Image.Transpose.ROTATE_270):
            fixed = upright(img.transpose(k))
            ok += fixed.size == img.size and _close(fixed, img)
    assert ok >= 10  # of 12


def test_upright_page_is_left_alone():
    b, _ = render_page(["2x+3=7", "2x=4", "x=2"], seed=7)
    img = load_rgb(b)
    assert upright(img).size == img.size


def _close(a, b):
    import numpy as np
    x = np.asarray(a.convert("L"), dtype=float)
    y = np.asarray(b.convert("L"), dtype=float)
    return np.abs(x - y).mean() < 3
