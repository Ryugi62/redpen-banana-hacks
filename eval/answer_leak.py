"""How often does the reasoning baseline give the answer away?

For slipped equation pages whose final line is wrong, check whether the reasoned baseline's explanation
contains the correct solution value. RedPen's hint notes never contain digits (tests/test_domain_markup.py).
Uses only cached model outputs (eval/cache) from eval/baseline_reasoned.py.

python -m eval.answer_leak synthetic-gemma-4-26b-a4b-it-n150 --per 30
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re

import sympy as sp

from eval.baseline_reasoned import PROMPT, PROMPT_NO_ANSWER, SCHEMA
from eval.run import HERE
from eval.seeded import generate
from eval.synth import render_page
from redpen.adapters.imageio import load_rgb, normalise_bytes
from redpen.domain.algebra import _solution_set, _symbols, parse_line


_STATES = r"(?:=|\bis\b|\bbe\b|\bequals?\b|\bgets?\b|\bgives?\b|\bresults?\s+in\b|\bresulting\s+in\b|\bto\s+get\b)"


def mentions(text: str, values) -> bool:
    """Strict: the correct value is STATED ("x = 5", "should be 5", "results in 5"), not merely any number."""
    return any(re.search(_STATES + r"\s*\(?\s*" + re.escape(str(v)) + r"(?![0-9/a-zA-Z^(]|\.[0-9])", text, flags=re.I) for v in values)


def appears(text: str, values) -> bool:
    """Loose: the value appears anywhere as a number (used to skip pages whose final answer is already right)."""
    t = text.replace(" ", "")
    return any(re.search(r"(?<![0-9/.])" + re.escape(str(v)) + r"(?![0-9/.])", t) for v in values)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--per", type=int, default=30)
    ap.add_argument("--no-answer", action="store_true", help="check the baseline that was told not to reveal the answer")
    a = ap.parse_args()
    prompt = PROMPT_NO_ANSWER if a.no_answer else PROMPT
    d = json.load(open(os.path.join(HERE, "results", f"{a.results}.json")))
    model = d["summary"]["model"]
    items = generate(a.per)
    pages, leaks = 0, []
    for r in d["rows"]:
        if r["gt"] is None:
            continue
        it = items[r["i"]]
        try:
            l0 = parse_line(it.lines[0])
            syms = _symbols(l0)
            if l0.kind == "expr" or len(syms) != 1:
                continue
            vals = [sp.nsimplify(v) for v in _solution_set(l0, syms[0])]
        except Exception:
            continue
        if appears(it.lines[-1], vals):
            continue  # the student's own final answer is right: nothing to give away
        img, _ = render_page(it.lines, seed=5000 + r["i"], hard=(r["i"] % 4 == 0))
        buf = io.BytesIO()
        load_rgb(normalise_bytes(img)).save(buf, format="JPEG", quality=88)
        key = hashlib.sha1((model + prompt + json.dumps(SCHEMA)).encode() + buf.getvalue()).hexdigest()
        path = os.path.join(HERE, "cache", f"{key}.json")
        if not os.path.exists(path):
            continue
        out = json.load(open(path))
        pages += 1
        if mentions(out.get("reasoning", ""), vals):
            leaks.append({"i": r["i"], "lines": it.lines, "answer": [str(v) for v in vals], "reasoning": out.get("reasoning", "")})
    res = {"pages": pages, "reasoning_reveals_answer": len(leaks), "examples": leaks}
    json.dump(res, open(os.path.join(HERE, "results", f"{a.results}-answer-leak{'-noanswer' if a.no_answer else ''}.json"), "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("pages", "reasoning_reveals_answer")}))


if __name__ == "__main__":
    main()
