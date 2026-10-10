"""Render the three demo samples (synthetic handwriting) and their recorded results."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.synth import render_page  # noqa: E402
from redpen.adapters.recorded import RecordedTranscriber  # noqa: E402
from redpen.adapters.renderer import InkRenderer  # noqa: E402
from redpen.adapters.segmenter import ProjectionSegmenter  # noqa: E402
from redpen.application.grade import GradePage  # noqa: E402
from redpen.infrastructure.service import to_json  # noqa: E402

SAMPLES = {
    "s1": (["3x-5=10", "3x=5", "x=5/3"], 3),
    "s2": (["x^2+2x=6x", "x^2=4x", "x=4"], 21),
    "s3": (["x^2-5x+6=0", "(x-2)(x-3)=0", "x=2 or x=3"], 8),
}

out_dir = os.path.join(os.path.dirname(__file__), "..", "public", "samples")
os.makedirs(out_dir, exist_ok=True)
seeds = {k: int(sys.argv[i + 1]) for i, k in enumerate(SAMPLES) if len(sys.argv) > i + 1}
for sid, (lines, seed) in SAMPLES.items():
    seed = seeds.get(sid, seed)
    img, gt = render_page(lines, seed)
    open(os.path.join(out_dir, f"{sid}.jpg"), "wb").write(img)
    res = GradePage(ProjectionSegmenter(), RecordedTranscriber(lines), InkRenderer()).execute(img)
    data = to_json(res, "recorded sample reading (no model call)")
    json.dump(data, open(os.path.join(out_dir, f"{sid}.result.json"), "w"))
    print(sid, len(res.steps), "lines", [s["relation"] for s in data["steps"]], data["verdict"]["hint"])
