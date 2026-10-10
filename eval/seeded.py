"""Deterministic worked solutions with exactly one injected slip (or none).

Each item: lines (student notation), first_slip index or None, slip kind.
The generator writes lines as strings; it does not use the verifier.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction
from typing import List, Optional


@dataclass
class Item:
    lines: List[str]
    first_slip: Optional[int]
    kind: Optional[str]
    template: str


def fmt_num(v) -> str:
    v = Fraction(v)
    if v.denominator == 1:
        return str(v.numerator)
    return f"{v.numerator}/{v.denominator}"


def lin(a, b, var="x") -> str:
    """a*var + b in student notation."""
    a, b = Fraction(a), Fraction(b)
    if a == 0:
        return fmt_num(b)
    if a == 1:
        s = var
    elif a == -1:
        s = f"-{var}"
    else:
        s = f"{fmt_num(a)}{var}"
    if b > 0:
        s += f"+{fmt_num(b)}"
    elif b < 0:
        s += f"-{fmt_num(-b)}"
    return s


def finish(a, c, var="x") -> List[str]:
    """Lines solving a*x = c."""
    out = []
    if a != 1:
        out.append(f"{lin(a, 0, var)}={fmt_num(c)}")
    out.append(f"{var}={fmt_num(Fraction(c) / Fraction(a))}")
    return out


def t_two_step(r: random.Random, slip: Optional[str]):
    a = r.choice([2, 3, 4, 5, 6, 7])
    x = r.randint(-9, 9)
    b = r.choice([v for v in range(-12, 13) if v != 0])
    c = a * x + b
    lines = [f"{lin(a, b)}={c}"]
    kind = None
    rhs = c - b
    if slip == "sign":
        rhs, kind = c + b, "sign"
    elif slip == "arithmetic":
        rhs, kind = c - b + r.choice([-2, -1, 1, 2]), "arithmetic"
    lines.append(f"{lin(a, 0)}={rhs}")
    final = Fraction(rhs, a)
    if slip == "divide":
        final, kind = Fraction(rhs) * a if r.random() < 0.5 else Fraction(rhs - a), "arithmetic"
    lines.append(f"x={fmt_num(final)}")
    first = None if slip is None else (2 if slip == "divide" else 1)
    return lines, first, kind


def t_distribute(r: random.Random, slip: Optional[str]):
    a = r.choice([2, 3, 4, 5, -2, -3])
    b = r.choice([v for v in range(-9, 10) if v != 0])
    x = r.randint(-8, 8)
    c = a * (x + b)
    bs = f"+{b}" if b > 0 else f"-{-b}"
    lines = [f"{a}(x{bs})={c}"]
    ab = a * b
    kind = None
    if slip == "distribution":
        ab, kind = b, "distribution"
    elif slip == "sign" and a < 0:
        ab, kind = -a * b, "sign"
    elif slip == "sign":
        ab, kind = a * b, None  # handled at the next line
    lines.append(f"{lin(a, ab)}={c}")
    rhs = c - ab
    if slip == "sign" and kind is None:
        rhs, kind = c + ab, "sign"
        lines += finish(a, rhs)
        return lines, 2, kind
    lines += finish(a, rhs)
    return lines, (None if slip is None else 1), kind


def t_both_sides(r: random.Random, slip: Optional[str]):
    a, c = r.sample([2, 3, 4, 5, 6, 7, 8, 9], 2)
    x = r.choice([v for v in range(-6, 7) if v != 0])
    b = r.choice([v for v in range(-10, 11) if v != 0])
    d = a * x + b - c * x
    if slip == "dropped_term" and d == 0:
        d = 1
    lines = [f"{lin(a, b)}={lin(c, d)}"]
    k = a - c
    rhs = d - b
    kind = None
    if slip == "sign":
        k, kind = a + c, "sign"
    elif slip == "dropped_term":
        lines.append(f"{lin(k, 0)}={fmt_num(d)}")
        lines += [f"x={fmt_num(Fraction(d, k))}"]
        return lines, 1, "dropped_term"
    elif slip == "arithmetic":
        rhs, kind = d - b + r.choice([-3, -1, 1, 3]), "arithmetic"
    lines.append(f"{lin(k, 0)}={fmt_num(rhs)}")
    lines.append(f"x={fmt_num(Fraction(rhs, k))}")
    return lines, (None if slip is None else 1), kind


def t_quadratic(r: random.Random, slip: Optional[str]):
    p, q = r.sample([v for v in range(-7, 8) if v != 0], 2)
    while p == -q:
        p, q = r.sample([v for v in range(-7, 8) if v != 0], 2)
    s, m = -(p + q), p * q  # (x-p)(x-q) = x^2 + s x + m
    def pm(v):
        return f"+{v}" if v > 0 else f"-{-v}"
    poly = "x^2" + (pm(s) + "x" if s not in (0, 1, -1) else ("+x" if s == 1 else "-x" if s == -1 else "")) + pm(m)
    lines = [f"{poly}=0"]
    kind = None
    pp, qq = p, q
    if slip == "sign":
        pp, qq, kind = -p, -q, "sign"
        lines.append(f"(x{pm(-pp)})(x{pm(-qq)})=0")
        lines.append(f"x={pp} or x={qq}")
        return lines, 1, kind
    lines.append(f"(x{pm(-p)})(x{pm(-q)})=0")
    if slip == "lost_solution":
        lines.append(f"x={p}")
        return lines, 2, "lost_solution"
    if slip == "root_sign":
        lines.append(f"x={-p} or x={-q}")
        return lines, 2, "sign"
    lines.append(f"x={p} or x={q}")
    return lines, None, None


def t_simplify(r: random.Random, slip: Optional[str]):
    a, c = r.sample([2, 3, 4, 5, 6], 2)
    b, d = r.choice([1, 2, 3, 4, 5, -1, -2, -3]), r.choice([1, 2, 3, 4, -4, -5, -2])
    def pm(v):
        return f"+{v}" if v > 0 else f"-{-v}"
    lines = [f"{a}(x{pm(b)})+{c}(x{pm(d)})"]
    t1, t2 = a * b, c * d
    kind = None
    if slip == "distribution":
        t1, kind = b, "distribution"
    lines.append(f"{a}x{pm(t1)}+{c}x{pm(t2)}")
    const = t1 + t2
    coef = a + c
    if slip == "arithmetic":
        const, kind = t1 + t2 + r.choice([-2, -1, 1, 2]), "arithmetic"
        lines.append(f"{coef}x{pm(const) if const else ''}")
        return lines, 2, kind
    if slip == "sign":
        const, kind = t1 - t2, "sign"
        lines.append(f"{coef}x{pm(const) if const else ''}")
        return lines, (2 if t2 != 0 else None), kind
    lines.append(f"{coef}x{pm(const) if const else ''}")
    return lines, (None if slip is None else 1), kind


TEMPLATES = {
    "two_step": (t_two_step, [None, "sign", "arithmetic", "divide"]),
    "distribute": (t_distribute, [None, "distribution", "sign"]),
    "both_sides": (t_both_sides, [None, "sign", "dropped_term", "arithmetic"]),
    "quadratic": (t_quadratic, [None, "sign", "lost_solution", "root_sign"]),
    "simplify": (t_simplify, [None, "distribution", "arithmetic", "sign"]),
}


def generate(n_per_template: int = 80, seed: int = 2026) -> List[Item]:
    r = random.Random(seed)
    items: List[Item] = []
    for name, (fn, slips) in TEMPLATES.items():
        for i in range(n_per_template):
            slip = slips[i % len(slips)]
            lines, first, kind = fn(r, slip)
            items.append(Item(lines, first, kind, name))
    return items
