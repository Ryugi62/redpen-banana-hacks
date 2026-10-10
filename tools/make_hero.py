"""public/hero.jpg: the home screen's first image: the notebook page as it comes back, marked (sample s4, real model run)."""
import base64
import io
import json
import os

from PIL import Image

root = os.path.join(os.path.dirname(__file__), "..")
res = json.load(open(os.path.join(root, "public", "samples", "s4.result.json")))
photo = Image.open(os.path.join(root, "public", "samples", "s4.jpg")).convert("RGB")
marked = Image.open(io.BytesIO(base64.b64decode(res["image"].split(",")[1]))).convert("RGB")
boxes = [st["box"] for st in res["steps"] if st["box"]]
x0 = max(0, min(b[0] for b in boxes) - 50)
y0 = max(0, min(b[1] for b in boxes) - 40)
y1 = min(marked.height, max(b[3] for b in boxes) + 50)
out = marked.crop((x0, y0, marked.width, y1))
out = out.resize((900, out.height * 900 // out.width), Image.LANCZOS)
out.save(os.path.join(root, "public", "hero.jpg"), quality=86)
print(out.size)
