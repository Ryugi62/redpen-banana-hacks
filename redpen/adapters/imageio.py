"""Image decoding helpers shared by adapters (EXIF orientation, size cap)."""
from __future__ import annotations

import io

from PIL import Image, ImageOps

MAX_SIDE = 1600


def load_rgb(data: bytes, max_side: int = MAX_SIDE) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    w, h = img.size
    s = max(w, h)
    if s > max_side:
        k = max_side / s
        img = img.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
    return img


def normalise_bytes(data: bytes, max_side: int = MAX_SIDE) -> bytes:
    """Decode + orient + downscale once, so every adapter sees the same pixels."""
    buf = io.BytesIO()
    load_rgb(data, max_side).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
