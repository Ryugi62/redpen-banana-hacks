"""Demo samples recorded from a REAL model run (not ground truth).

Each sample page is rendered from human pen strokes (eval/synth.py), then graded once through the
production pipeline (CV lines -> vision model reads -> SymPy verifies -> zoomed re-read -> red pen).
The JSON saved is exactly what /api/grade returned for it, so clicking a sample replays a real reading.

GEMINI_API_KEY=... python tools/record_samples.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.synth import render_page  # noqa: E402
from redpen.adapters.renderer import InkRenderer  # noqa: E402
from redpen.adapters.segmenter import ProjectionSegmenter  # noqa: E402
from redpen.application.grade import GradePage  # noqa: E402
from redpen.infrastructure.service import build_transcriber, to_json  # noqa: E402

SAMPLES = {  # id: (lines, seed, hard page = paper texture + tilt + blur)
    "s1": (["3x-5=10", "3x=5", "x=5/3"], 3, False),
    "s2": (["x^2+2x=6x", "x^2=4x", "x=4"], 21, False),
    "s3": (["x^2-5x+6=0", "(x-2)(x-3)=0", "x=2 or x=3"], 8, False),
    "s4": (["4(x-2)=2x+6", "4x-2=2x+6", "2x=8", "x=4", "4(4-2)=2(4)+6"], 14, True),
}

out_dir = os.path.join(os.path.dirname(__file__), "..", "public", "samples")
only = set(sys.argv[1:])
for sid, (lines, seed, hard) in SAMPLES.items():
    if only and sid not in only:
        continue
    img, _ = render_page(lines, seed, hard=hard)
    tr = build_transcriber()
    res = GradePage(ProjectionSegmenter(), tr, InkRenderer(), locator=tr).execute(img)
    data = to_json(res, tr.used)
    data["recorded"] = True
    open(os.path.join(out_dir, f"{sid}.jpg"), "wb").write(img)
    json.dump(data, open(os.path.join(out_dir, f"{sid}.result.json"), "w"))
    print(sid, tr.used, [(s["text"], s["relation"]) for s in data["steps"]], data["verdict"]["first_slip_line"],
          data["verdict"]["hint"], data["verdict"]["uncertain_lines"], data["timings_ms"])
