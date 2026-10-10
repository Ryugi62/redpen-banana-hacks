"""Write the README results table from eval/results/*.json (numbers are copied, never typed).

python tools/results_table.py synthetic-gemma-4-26b-a4b-it-n150 real-gemma-4-26b-a4b-it
"""
import json
import math
import os
import re
import sys
from math import comb

ROOT = os.path.join(os.path.dirname(__file__), "..")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (c - h, c + h)


def correct_pipe(r):
    return (r["gt"] is None and not r["pred_flagged"]) or (r["gt"] is not None and r["pred_line"] == r["gt"])


def correct_base(r):
    b = r["baseline"]
    return b is not None and ((r["gt"] is None and b == 0) or (r["gt"] is not None and b == r["gt"] + 1))


def mcnemar_p(rows):
    b = sum(1 for r in rows if correct_pipe(r) and not correct_base(r))
    c = sum(1 for r in rows if correct_base(r) and not correct_pipe(r))
    n = b + c
    if n == 0:
        return 1.0, b, c
    p = 2 * sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, p), b, c


def pct(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / max(1, n):.0f} % ({100 * lo:.0f}–{100 * hi:.0f})"


def stats(name):
    d = json.load(open(os.path.join(ROOT, "eval", "results", f"{name}.json")))
    rows = [r for r in d["rows"] if r.get("mode") != "error"]
    clean = [r for r in rows if r["gt"] is None]
    slipped = [r for r in rows if r["gt"] is not None]
    p, b, c = mcnemar_p(rows)
    return {
        "set": d["summary"]["set"], "pages": len(rows), "clean": len(clean), "slipped": len(slipped),
        "pipe_overall": pct(sum(map(correct_pipe, rows)), len(rows)),
        "base_overall": pct(sum(map(correct_base, rows)), len(rows)),
        "pipe_slip": pct(sum(map(correct_pipe, slipped)), len(slipped)),
        "base_slip": pct(sum(map(correct_base, slipped)), len(slipped)),
        "pipe_fa": pct(sum(r["pred_flagged"] for r in clean), len(clean)),
        "base_fa": pct(sum((r["baseline"] or 0) != 0 for r in clean), len(clean)),
        "pipe_wrong": sum(1 for r in rows if r["pred_flagged"] and not correct_pipe(r)),
        "base_wrong": sum(1 for r in rows if (r["baseline"] or 0) != 0 and not correct_base(r)),
        "asked": sum(1 for r in rows if r.get("uncertain") and not r["pred_flagged"]),
        "p": p, "b": b, "c": c,
    }


def table(names, other="same model asked directly"):
    ss = [stats(n) for n in names]
    head = "| | " + " | ".join(f"{s['set']} pages (n={s['pages']}: {s['slipped']} with a slip, {s['clean']} correct)" for s in ss) + " |"
    sep = "|---|" + "---|" * len(ss)
    rows = [
        ("**Right answer about the page**, RedPen", "pipe_overall"), (f"Right answer about the page, {other}", "base_overall"),
        ("First slip found on the right line, RedPen", "pipe_slip"), (f"First slip found on the right line, {other}", "base_slip"),
        ("**Correct pages wrongly accused**, RedPen", "pipe_fa"), (f"Correct pages wrongly accused, {other}", "base_fa"),
    ]
    out = [head, sep]
    for label, k in rows:
        out.append(f"| {label} | " + " | ".join(str(s[k]) for s in ss) + " |")
    out.append(f"| Pages where RedPen pointed at a wrong line / {other} | " + " | ".join(f"{s['pipe_wrong']} / {s['base_wrong']}" for s in ss) + " |")
    out.append("| Pages where RedPen asked \"?\" instead of accusing | " + " | ".join(str(s["asked"]) for s in ss) + " |")
    out.append(f"| Paired comparison (pages only RedPen got right / only {other} got right, exact McNemar p) | " + " | ".join(f"{s['b']} / {s['c']}, " + (f"p = {s['p']:.3f}" if s['p'] >= 0.001 else "p < 0.001") for s in ss) + " |")
    out.append("")
    out.append("Percentages with 95 % Wilson intervals in brackets.")
    return "\n".join(out)


def put(s, tag, t):
    return re.sub(rf"(<!-- {tag}:start -->)(.*?)(<!-- {tag}:end -->)", lambda m: m.group(1) + "\n" + t + "\n" + m.group(3), s, flags=re.S)


if __name__ == "__main__":
    args = sys.argv[1:]
    reasoned = []
    if "--reasoned" in args:
        k = args.index("--reasoned")
        args, reasoned = args[:k], args[k + 1:]
    t = table(args)
    path = os.path.join(ROOT, "README.md")
    s = open(path, encoding="utf-8").read()
    if reasoned:
        s = put(s, "reasoned", table(reasoned, "same model told to transcribe and reason step by step"))
    s = re.sub(r"(<!-- results:start -->)(.*?)(<!-- results:end -->)", lambda m: m.group(1) + "\n" + t + "\n" + m.group(3), s, flags=re.S)
    s = s.replace("RESULTS_TABLE", "<!-- results:start -->\n" + t + "\n<!-- results:end -->")
    open(path, "w", encoding="utf-8").write(s)
    print(t)
