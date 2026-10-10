"""docs/pipeline.png: photo -> numbered lines -> verdict -> marked page (from sample s1)."""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from redpen.adapters.gemini import mark_boxes  # noqa: E402
from redpen.adapters.imageio import load_rgb  # noqa: E402
from redpen.domain.model import LineBox  # noqa: E402

root = os.path.join(os.path.dirname(__file__), "..")
sid = sys.argv[1] if len(sys.argv) > 1 else "s1"
photo = load_rgb(open(os.path.join(root, "public", "samples", f"{sid}.jpg"), "rb").read())
res = json.load(open(os.path.join(root, "public", "samples", f"{sid}.result.json")))
boxes = [LineBox(*s["box"]) for s in res["steps"]]
marked_boxes = mark_boxes(photo, boxes)
marked = Image.open(__import__("io").BytesIO(base64.b64decode(res["image"].split(",")[1]))).convert("RGB")

def crop(im):
    xs = [b.x0 for b in boxes] + [b.x1 for b in boxes]
    ys = [b.y0 for b in boxes] + [b.y1 for b in boxes]
    pad = 70
    return im.crop((max(0, min(xs) - pad - 40), max(0, min(ys) - pad), min(im.width, max(xs) + 330), min(im.height, max(ys) + pad + 40)))

panels = [crop(photo), crop(marked_boxes), None, crop(marked)]
H = 360
panels = [p.resize((int(p.width * H / p.height), H)) if p else None for p in panels]
# text panel: readings + relations
tw = 380
tp = Image.new("RGB", (tw, H), (255, 255, 255))
d = ImageDraw.Draw(tp)
try:
    f = ImageFont.load_default(size=26)
    fs = ImageFont.load_default(size=20)
except TypeError:
    f = fs = ImageFont.load_default()
y = 60
col = {"start": (18, 161, 80), "equivalent": (18, 161, 80), "not_equivalent": (208, 22, 42)}
for i, s in enumerate(res["steps"]):
    d.text((24, y), f"{i + 1}  {s['text']}", fill=(25, 31, 40), font=f)
    lab = {"start": "start", "equivalent": "holds", "not_equivalent": "BREAKS"}.get(s["relation"], s["relation"])
    d.text((260, y + 4), lab, fill=col.get(s["relation"], (120, 120, 120)), font=fs)
    y += 60
d.text((24, y + 10), f"hint: {res['verdict']['hint'] or '-'}", fill=(208, 22, 42), font=fs)
panels[2] = tp
titles = ["1  your photo", "2  CV finds lines, model reads", "3  SymPy verifies", "4  your page, marked"]
gap = 28
W = sum(p.width for p in panels) + gap * (len(panels) + 1)
out = Image.new("RGB", (W, H + 90), (246, 247, 249))
dd = ImageDraw.Draw(out)
x = gap
for p, t in zip(panels, titles):
    out.paste(p, (x, 64))
    dd.text((x, 22), t, fill=(25, 31, 40), font=f)
    x += p.width + gap
out.save(os.path.join(root, "docs", "pipeline.png"), optimize=True)
print(out.size)
