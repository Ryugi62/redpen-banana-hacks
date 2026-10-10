"""Build data/glyphs.json from Google MathWriting `symbols/` inks (CC BY-NC-SA 4.0).

Usage: python tools/build_glyphs.py <path-to-mathwriting-2024>/symbols data/glyphs.json
Keeps up to N human samples per needed glyph, normalises each to its own bbox and
simplifies strokes. Output keeps the dataset's licence (see data/README.md).
"""
import glob
import json
import math
import random
import re
import sys
import xml.etree.ElementTree as ET

NEED = list("0123456789abcdefghijklmnopqrstuvwxyz") + ["+", "-", "=", "(", ")", "/", "?", "!", ".", ",", "\\cdot", "\\times", "\\pm", "\\sqrt", "&lt;", "&gt;"]
ALIAS = {"&lt;": "<", "&gt;": ">", "\\cdot": "*", "\\times": "x*", "\\pm": "±", "\\sqrt": "√"}
PER = 14


def rdp(points, eps):
    if len(points) < 3:
        return points
    (x0, y0), (x1, y1) = points[0], points[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = math.hypot(dx, dy) or 1e-9
    dmax, idx = 0.0, 0
    for i, (x, y) in enumerate(points[1:-1], 1):
        d = abs(dy * x - dx * y + x1 * y0 - y1 * x0) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(points[: idx + 1], eps)[:-1] + rdp(points[idx:], eps)
    return [points[0], points[-1]]


def main(src, out):
    ns = {"i": "http://www.w3.org/2003/InkML"}
    by = {}
    files = sorted(glob.glob(f"{src}/*.inkml"))
    for f in files:
        txt = open(f, encoding="utf-8").read()
        label = re.search(r'type="label">(.*?)<', txt).group(1)
        if label not in NEED:
            continue
        by.setdefault(label, []).append(f)
    bank = {}
    rng = random.Random(2026)
    for label, fs in by.items():
        rng.shuffle(fs)
        samples = []
        for f in fs[:PER]:
            root = ET.parse(f).getroot()
            strokes = []
            for tr in root.findall("i:trace", ns):
                pts = [tuple(map(float, p.split()[:2])) for p in tr.text.strip().split(",")]
                strokes.append(pts)
            xs = [x for s in strokes for x, _ in s]
            ys = [y for s in strokes for _, y in s]
            x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
            scale = max(w, h) or 1.0
            norm = []
            for s in strokes:
                p = [((x - x0) / scale, (y - y0) / scale) for x, y in s]
                p = rdp(p, 0.012)
                norm.append([[round(x, 3), round(y, 3)] for x, y in p])
            samples.append({"w": round(w / scale, 3), "h": round(h / scale, 3), "s": norm})
        bank[ALIAS.get(label, label)] = samples
    json.dump({"source": "Google MathWriting (symbols), CC BY-NC-SA 4.0", "glyphs": bank}, open(out, "w"), separators=(",", ":"))
    print(out, {k: len(v) for k, v in bank.items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
