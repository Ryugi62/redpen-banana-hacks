"""Stronger baseline (round-2 judge request): the same vision model may transcribe every line and
reason step by step before naming the first wrong line. Same pages as an existing synthetic results file.

python -m eval.baseline_reasoned synthetic-gemma-4-26b-a4b-it-n150 --per 30
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from eval.run import CachedTranscriber, HERE
from eval.seeded import generate
from eval.synth import render_page
from redpen.adapters.gemini import VisionUnavailable
from redpen.adapters.imageio import load_rgb, normalise_bytes

PROMPT = """This photo shows a student's handwritten maths solution. Number the written lines of working 1, 2, 3, ... from top to bottom
(ignore lines that are only words). First copy every line exactly as written. Then check, step by step, whether each line
follows correctly from the line before it, showing your reasoning. Finally give first_wrong_line: the number of the FIRST line
that contains a mistake, or 0 if the whole solution is correct."""

PROMPT_NO_ANSWER = PROMPT + """
You are tutoring the student: never state the correct answer, the correct value of any line, or a corrected line.
In your reasoning describe only where and what kind of mistake it is (for example "a sign error when moving a term")."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "lines": {"type": "ARRAY", "items": {"type": "STRING"}},
        "reasoning": {"type": "STRING"},
        "first_wrong_line": {"type": "INTEGER"},
    },
    "required": ["lines", "reasoning", "first_wrong_line"],
    "propertyOrdering": ["lines", "reasoning", "first_wrong_line"],
}


def answer(img: bytes, model: str, prompt: str = PROMPT):
    tr = CachedTranscriber(model=model, timeout=120)
    try:
        out = tr._call(prompt, load_rgb(img), SCHEMA)
    except VisionUnavailable:
        return None
    try:
        return int(out.get("first_wrong_line"))
    except (TypeError, ValueError, AttributeError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--per", type=int, default=30)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-answer", action="store_true", help="tell the model not to reveal the answer")
    a = ap.parse_args()
    prompt = PROMPT_NO_ANSWER if a.no_answer else PROMPT
    suffix = "-noanswer-baseline" if a.no_answer else "-reasoned-baseline"
    path = os.path.join(HERE, "results", f"{a.results}.json")
    d = json.load(open(path))
    model = d["summary"]["model"]
    items = generate(a.per)

    def one(r):
        if "file" in r:  # real crops
            from redpen.adapters.orient import upright_bytes
            img = upright_bytes(normalise_bytes(open(os.path.join(HERE, "real", r["file"]), "rb").read()))
            return {**r, "baseline_reasoned": answer(img, model, prompt)}
        it = items[r["i"]]
        img, _ = render_page(it.lines, seed=5000 + r["i"], hard=(r["i"] % 4 == 0))
        return {**r, "baseline_reasoned": answer(normalise_bytes(img), model, prompt)}

    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(one, d["rows"]))
    for r in rows:
        print(json.dumps({k: r.get(k) for k in ("i", "file", "gt", "pred_line", "baseline", "baseline_reasoned")}), flush=True)
    out = os.path.join(HERE, "results", f"{a.results}{suffix}.json")
    json.dump({"summary": {**d["summary"], "baseline": "reasoned (transcribe + step-by-step, same model)" + (", told not to reveal the answer" if a.no_answer else "")}, "rows": [
        {**r, "baseline_naive": r.get("baseline"), "baseline": r["baseline_reasoned"]} for r in rows]}, open(out, "w"), indent=1)
    print(out)


if __name__ == "__main__":
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("set GEMINI_API_KEY")
    main()
