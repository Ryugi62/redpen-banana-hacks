"""Crop algebra chains from real student answer sheets (images are NOT committed).

Source: Hugging Face dataset lokeshe09/handwritten-mathqa-vista_format (48 phone photos of grade-9
answer sheets; no licence stated, so images stay local and only labels/results are published).
Labels below were written by reading each crop; first_slip = 0-based index among maths lines.
"""
import json
import os
import sys

from redpen.adapters.imageio import load_rgb
from redpen.adapters.orient import upright

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/dev/bh-data/sheets")
OUT = os.path.join(os.path.dirname(__file__), "real")

CROPS = [
    ("004", (0.22, 0.285, 0.60, 0.395), ["5((5)^2-3(10))", "=5(-4)", "=-20"], 1, "25-30 is -5, not -4"),
    ("005", (0.10, 0.295, 0.47, 0.445), ["5((5)^2-3(10))", "=5(-4)", "=-20"], 1, "25-30 is -5, not -4"),
    ("021", (0.10, 0.615, 0.60, 0.805), ["(5)^2+2(10)-3abc=-25", "25+20-3abc=-25", "45-3abc=-25", "3abc=-25-45", "3abc=-70", "abc=-70/3"], 3, "moving 45 across: 3abc = 25+45"),
    ("032", (0.17, 0.188, 0.52, 0.28), ["(2)^3+(2)^2-2(2)+a=0", "8+4-4+a=0", "8+a=0"], None, "correct"),
    ("029", (0.13, 0.24, 0.64, 0.425), ["=2x^3+5x^2-5x-2", "=2(1)^3+5(1)^2-5(1)-2", "=2+5-5-2", "=7-7", "=0"], None, "correct (value substitution)"),
    ("029", (0.24, 0.758, 0.60, 0.87), ["-7+sqrt((7)^2-4*2*2)", "-7+sqrt(49-16)", "-7+sqrt(33)"], None, "correct (x used as times sign)"),
    ("015", (0.10, 0.26, 0.74, 0.35), ["p(1)=2(1)^3+5(1)^2-5(1)-2", "=2+5-5-2=0"], None, "correct"),
]

os.makedirs(OUT, exist_ok=True)
labels = []
for n, (sheet, (x0, y0, x1, y1), lines, slip, note) in enumerate(CROPS):
    img = upright(load_rgb(open(os.path.join(SRC, f"{sheet}.jpg"), "rb").read()))
    W, H = img.size
    crop = img.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
    name = f"real{n + 1:02d}-{sheet}.jpg"
    crop.save(os.path.join(OUT, name), quality=92)
    labels.append({"file": name, "sheet": sheet, "lines": lines, "first_slip": slip, "note": note})
json.dump(labels, open(os.path.join(OUT, "labels.json"), "w"), indent=1)
print(len(labels), "crops")
