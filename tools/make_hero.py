"""public/hero.jpg: the home screen's first image — a photo and the same page marked (sample s4, real model run)."""
import base64
import io
import json
import os

from PIL import Image

root = os.path.join(os.path.dirname(__file__), "..")
res = json.load(open(os.path.join(root, "public", "samples", "s4.result.json")))
photo = Image.open(os.path.join(root, "public", "samples", "s4.jpg")).convert("RGB")
marked = Image.open(io.BytesIO(base64.b64decode(res["image"].split(",")[1]))).convert("RGB")
box = (60, 40, 820, 520)
a, b = photo.crop(box), marked.crop(box)
W, H, gap = a.width * 2 + 24, a.height, 24
out = Image.new("RGB", (W, H), (255, 255, 255))
out.paste(a, (0, 0))
out.paste(b, (a.width + gap, 0))
out = out.resize((W * 900 // W, H * 900 // W), Image.LANCZOS)
out.save(os.path.join(root, "public", "hero.jpg"), quality=86)
print(out.size)
