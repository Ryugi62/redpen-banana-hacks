"""End-to-end evaluation: RedPen pipeline vs. the same vision model asked directly.

python -m eval.run synth --model gemma-4-31b-it --n 60
python -m eval.run real  --model gemini-3.6-flash          (eval/real/labels.json, images not in repo)

Model responses are cached in eval/cache/ so numbers can be re-derived without new calls.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from PIL import Image

from eval.seeded import generate
from eval.synth import render_page
from redpen.adapters.gemini import GeminiTranscriber, VisionUnavailable
from redpen.adapters.imageio import load_rgb, normalise_bytes
from redpen.adapters.orient import upright_bytes
from redpen.adapters.segmenter import ProjectionSegmenter
from redpen.application.grade import GradePage, plausible_lines
from redpen.domain.model import LineBox

HERE = os.path.dirname(__file__)
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

BASELINE_PROMPT = """This photo shows a student's handwritten maths solution. Number the written lines of working 1, 2, 3, ... from top to bottom
(ignore lines that are only words). Is every line a correct consequence of the line before it?
Return JSON {"first_wrong_line": N} where N is the number of the FIRST line that contains a mistake, or 0 if the whole solution is correct."""

BASELINE_SCHEMA = {"type": "OBJECT", "properties": {"first_wrong_line": {"type": "INTEGER"}}, "required": ["first_wrong_line"]}


class NullRenderer:
    def render(self, image, steps, plan):
        return b""


class CachedTranscriber(GeminiTranscriber):
    """Same adapter, with a disk cache keyed by model + prompt + image + boxes."""

    def _call(self, prompt, img, schema):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        key = hashlib.sha1((self.model + prompt + json.dumps(schema)).encode() + buf.getvalue()).hexdigest()
        path = os.path.join(CACHE, f"{key}.json")
        if os.path.exists(path):
            return json.load(open(path))
        for attempt in range(4):
            try:
                out = super()._call(prompt, img, schema)
                json.dump(out, open(path, "w"))
                return out
            except VisionUnavailable as e:
                if any(c in str(e) for c in ("429", "500", "503", "timed out")) and attempt < 3:
                    time.sleep(15 * (attempt + 1))
                    continue
                raise
        return {}


def gt_index_for(pred_box: LineBox, gt_boxes: List[LineBox]) -> Optional[int]:
    best, idx = 0.0, None
    for i, g in enumerate(gt_boxes):
        iou = pred_box.iou(g)
        if iou > best:
            best, idx = iou, i
    return idx if best >= 0.3 else None


def run_pipeline(img: bytes, model: str):
    tr = CachedTranscriber(model=model, timeout=90)
    res = GradePage(ProjectionSegmenter(), tr, NullRenderer(), locator=tr).execute(img)
    return res


def run_baseline(img: bytes, model: str) -> Optional[int]:
    tr = CachedTranscriber(model=model, timeout=90)
    try:
        out = tr._call(BASELINE_PROMPT, load_rgb(img), BASELINE_SCHEMA)
    except VisionUnavailable:
        return None
    try:
        v = int(out.get("first_wrong_line"))
    except (TypeError, ValueError, AttributeError):
        return None
    return v


def norm(t: str) -> str:
    return t.replace(" ", "").replace("*", "").lower()


def eval_synth(model: str, n: int, workers: int, per: int = 12):
    items = generate(per)
    # balanced pick: every template, slipped and clean
    picked = []
    for i, it in enumerate(items):
        if len(picked) >= n:
            break
        if i % max(1, len(items) // n) == 0:
            picked.append((i, it))
    rows = []

    def one(arg):
        i, it = arg
        img, gt = render_page(it.lines, seed=5000 + i, hard=(i % 4 == 0))
        img = normalise_bytes(img)
        # GT boxes must be in the same (normalised) pixel space: synth pages are <= 1600 px, unchanged
        try:
            res = run_pipeline(img, model)
        except VisionUnavailable as e:
            return {"i": i, "template": it.template, "gt": it.first_slip, "error": str(e), "pred_line": None, "baseline": None, "mode": "error"}
        pred = res.verdict.first_slip
        pred_gt = None
        if pred is not None and res.steps[pred].box is not None:
            pred_gt = gt_index_for(res.steps[pred].box, gt)
        base = run_baseline(img, model)
        reads = []
        for s in res.steps:
            gi = gt_index_for(s.box, gt) if s.box else None
            if gi is not None:
                reads.append(norm(s.text) == norm(it.lines[gi]))
        return {
            "i": i, "template": it.template, "kind": it.kind, "gt": it.first_slip, "lines": it.lines,
            "pred_line": pred_gt, "pred_flagged": pred is not None, "mode": res.mode,
            "relations": [r.value for r in res.verdict.relations], "texts": [s.text for s in res.steps],
            "baseline": base, "reads_exact": reads, "hard": i % 4 == 0,
            "rechecked": res.rechecked, "uncertain": [u for u in res.uncertain],
        }

    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(one, picked):
            rows.append(r)
            print(json.dumps({k: r[k] for k in ("i", "template", "gt", "pred_line", "baseline", "mode")}), flush=True)
    return summarise(rows, model, "synthetic")


def summarise(rows, model, name):
    errors = [r for r in rows if r.get("mode") == "error"]
    rows = [r for r in rows if r.get("mode") != "error"]
    def correct_pipe(r):
        return (r["gt"] is None and not r["pred_flagged"]) or (r["gt"] is not None and r["pred_line"] == r["gt"])

    def correct_base(r):
        if r["baseline"] is None:
            return False
        return (r["gt"] is None and r["baseline"] == 0) or (r["gt"] is not None and r["baseline"] == r["gt"] + 1)

    slipped = [r for r in rows if r["gt"] is not None]
    clean = [r for r in rows if r["gt"] is None]
    reads = [x for r in rows for x in r["reads_exact"]]
    summary = {
        "set": name, "model": model, "pages": len(rows), "slipped": len(slipped), "clean": len(clean),
        "pipeline_first_slip_acc": sum(correct_pipe(r) for r in slipped) / max(1, len(slipped)),
        "pipeline_false_alarm": sum(r["pred_flagged"] for r in clean) / max(1, len(clean)),
        "pipeline_overall_acc": sum(correct_pipe(r) for r in rows) / max(1, len(rows)),
        "baseline_first_slip_acc": sum(correct_base(r) for r in slipped) / max(1, len(slipped)),
        "baseline_false_alarm": sum((r["baseline"] or 0) != 0 for r in clean) / max(1, len(clean)),
        "baseline_overall_acc": sum(correct_base(r) for r in rows) / max(1, len(rows)),
        "line_read_exact": sum(reads) / max(1, len(reads)),
        "model_located_pages": sum(r["mode"] == "model-located" for r in rows),
        "baseline_no_answer": sum(r["baseline"] is None for r in rows),
        "pages_skipped_model_error": len(errors),
        # three-way outcome: a tutor that asks "check this line?" is better than one that accuses wrongly
        "pipeline_asked_instead": sum(1 for r in rows if r.get("uncertain") and not r["pred_flagged"]),
        "pipeline_wrong_accusations": sum(1 for r in rows if r["pred_flagged"] and not correct_pipe(r)),
        "baseline_wrong_accusations": sum(1 for r in rows if (r["baseline"] or 0) != 0 and not correct_base(r)),
        "pipeline_missed_slip_silently": sum(1 for r in slipped if not r["pred_flagged"] and not r.get("uncertain")),
        "baseline_missed_slip": sum(1 for r in slipped if (r["baseline"] or 0) == 0),
    }
    out = os.path.join(HERE, "results", f"{name}-{model}{os.environ.get('EVAL_TAG', '')}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"summary": summary, "rows": rows}, open(out, "w"), indent=1)
    print(json.dumps(summary, indent=1))
    return summary


def eval_real(model: str, workers: int):
    labels = json.load(open(os.path.join(HERE, "real", "labels.json")))
    rows = []

    def one(lab):
        try:
            return _one_real(lab)
        except VisionUnavailable as e:
            return {"file": lab["file"], "gt": lab["first_slip"], "error": str(e), "pred_line": None, "baseline": None, "mode": "error"}

    def _one_real(lab):
        img = upright_bytes(normalise_bytes(open(os.path.join(HERE, "real", lab["file"]), "rb").read()))
        res = run_pipeline(img, model)
        maths_idx = [i for i, s in enumerate(res.steps) if s.kind != "prose"]
        pred = res.verdict.first_slip
        # map predicted step to the labelled maths-line number by reading order among maths lines
        pred_line = maths_idx.index(pred) if pred is not None and pred in maths_idx else None
        if pred is not None and lab.get("lines"):
            # prefer text match against labelled lines when available
            for j, t in enumerate(lab["lines"]):
                if norm(t) == norm(res.steps[pred].text):
                    pred_line = j
        base = run_baseline(img, model)
        return {"file": lab["file"], "gt": lab["first_slip"], "lines": lab.get("lines"), "pred_line": pred_line,
                "pred_flagged": pred is not None, "mode": res.mode, "relations": [r.value for r in res.verdict.relations],
                "texts": [s.text for s in res.steps], "baseline": base, "reads_exact": [],
                "rechecked": res.rechecked, "uncertain": [u for u in res.uncertain]}

    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(one, labels):
            rows.append(r)
            print(json.dumps({k: r[k] for k in ("file", "gt", "pred_line", "baseline", "mode")}), flush=True)
    return summarise(rows, model, "real")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("set", choices=["synth", "real"])
    ap.add_argument("--model", default="gemma-4-31b-it")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--per", type=int, default=12, help="seeded solutions per template (5 templates)")
    ap.add_argument("--tag", default="", help="suffix for the results file")
    a = ap.parse_args()
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("set GEMINI_API_KEY")
    if a.set == "synth":
        eval_synth(a.model, a.n, a.workers, a.per)
    else:
        eval_real(a.model, a.workers)
