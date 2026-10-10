"""Parsing and relating lines of algebra. Pure Python + SymPy (no I/O).

A line is one of:
  * Expression     e.g. ``2(x+3)``  (a leading ``=`` means "continues the previous expression")
  * Equation       e.g. ``2x+3=7``
  * SolutionList   e.g. ``x=2 or x=3`` / ``x=2, x=-3`` / ``x=±2``
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, List, Optional, Sequence, Tuple

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from .model import Hint, Relation


class Unreadable(ValueError):
    """Text cannot be parsed as algebra (treated as a misread, never as wrong)."""


class Unsupported(ValueError):
    """Valid maths outside the supported scope (calculus, matrices, inequalities...)."""


_TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)
_LETTERS = {c: sp.Symbol(c) for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"}
_LOCALS = dict(_LETTERS, sqrt=sp.sqrt, pi=sp.pi)
_ALLOWED_WORDS = {"sqrt", "pi"}
_UNSUPPORTED_MARKERS = ("∫", "integral", "int(", "lim", "sum", "matrix", "[", "]", "d/dx", "dy/dx", "<", ">", "≤", "≥", "≠", "!=")
_UNITS = re.compile(r"(?<=[0-9)])\s*(?:sq\.?\s*)?(?:cm|mm|km|kg|m|g|s|units?|unit)(?:\^?[23])?\b")
_SAFE_CHARS = re.compile(r"^[0-9A-Za-z+\-*/^().=, ]*$")

_REPLACEMENTS = [
    ("−", "-"), ("–", "-"), ("—", "-"), ("·", "*"), ("×", "*"), ("÷", "/"), ("∙", "*"),
    ("²", "^2"), ("³", "^3"), ("√", "sqrt"), ("∠", ""), ("≠", "!="), ("\\cdot", "*"), ("\\times", "*"), ("\\div", "/"),
    ("{", "("), ("}", ")"), ("\\left", ""), ("\\right", ""), ("$", ""),
]


@dataclass(frozen=True)
class Line:
    kind: str  # "expr" | "eq" | "sols"
    exprs: Tuple[sp.Expr, ...]  # expr: (last piece,)  eq: (lhs - rhs,)  sols: (lhs_i - rhs_i, ...)
    sides: Tuple[Tuple[sp.Expr, sp.Expr], ...] = ()  # unevaluated (lhs, rhs) per equation, for hints
    raw: Optional[sp.Expr] = None  # unevaluated expression, for hints
    head: Optional[sp.Expr] = None  # expr chains: first piece (compared with the previous line)
    internal_slip: bool = False  # a chain like "a = b = c" where b != c
    raw_head: Optional[sp.Expr] = None  # unevaluated first piece (structure, for substitution detection)
    decimals: int = 0  # most digits written after a decimal point (rounded answers are accepted to that precision)


_LEAD = re.compile(r"^\s*(?:=>|⇒|->|→|∴|therefore\b|so\b|hence\b)\s*", re.I)
_TRAIL = re.compile(r"\s*(?://+|■|□|✓|✔|#+)\s*$")
_OR_V = re.compile(r"(?<=[0-9a-zA-Z)])\s+[vV]\s+(?=[a-zA-Z(\-0-9])")


def normalise(text: str) -> str:
    t = text.strip()
    t = _LEAD.sub("", t)  # students' arrows / "therefore" before a line
    t = _TRAIL.sub("", t)  # end-of-answer marks
    t = _OR_V.sub(" or ", t)  # "x=-1 v x=-3" means "or"
    for a, b in _REPLACEMENTS:
        t = t.replace(a, b)
    t = re.sub(r"\\frac\(([^()]*)\)\(([^()]*)\)", r"((\1)/(\2))", t)
    t = re.sub(r"\\sqrt", "sqrt", t)
    t = re.sub(r"\s+", " ", t).strip().rstrip(".;")
    t = _UNITS.sub("", t).replace("°", "").strip()
    return t


def _check_unsupported(t: str) -> None:
    low = t.lower()
    for m in _UNSUPPORTED_MARKERS:
        if m in low:
            raise Unsupported(m)


def _parse(t: str, evaluate: bool = True) -> sp.Expr:
    t = t.strip()
    if not t:
        raise Unreadable("empty")
    if not _SAFE_CHARS.match(t):
        raise Unreadable(f"characters: {t!r}")
    if len(t) > 160 or re.search(r"\d{16,}", t):
        raise Unreadable("too long")
    if re.search(r"\^[^+\-=]*\^", t) or re.search(r"\^\s*\(?\s*-?\d{3,}", t):
        raise Unsupported("huge power")  # power towers / huge exponents: outside school algebra, and slow
    for word in re.findall(r"[A-Za-z]{2,}", t):
        if word not in _ALLOWED_WORDS and not all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in word):
            raise Unreadable(word)
        if word not in _ALLOWED_WORDS and len(word) > 3:
            raise Unreadable(word)  # long letter runs are almost always misreads, not products
    try:
        e = parse_expr(t, local_dict=dict(_LOCALS), transformations=_TRANSFORMS, evaluate=evaluate)
    except Exception as exc:  # SymPy raises many types for malformed input
        raise Unreadable(str(exc)) from exc
    if not isinstance(e, sp.Expr):
        raise Unreadable(f"not an expression: {t!r}")
    return e


def _split_solutions(t: str) -> List[str]:
    parts = re.split(r"\s*(?:,|;|\bor\b|\band\b)\s*", t)
    parts = [p for p in parts if p]
    out: List[str] = []
    var = None
    for p in parts:
        if "=" in p:
            var = p.split("=")[0].strip()
        elif var:
            p = f"{var}={p}"
        if "±" in p or "+-" in p:
            p = p.replace("+-", "±")
            out += [p.replace("±", "+", 1), p.replace("±", "-", 1)]
        else:
            out.append(p)
    return out


def _chain_consistent(pieces: List[str]) -> bool:
    exprs = [_parse(p) for p in pieces]
    return all(expressions_equivalent(a, b) for a, b in zip(exprs, exprs[1:]))


def _decimals(t: str) -> int:
    return max((len(m) for m in re.findall(r"\d\.(\d+)", t)), default=0)


def parse_line(text: str) -> Line:
    from dataclasses import replace as _replace
    t = normalise(text)
    line = _parse_line(t)
    d = _decimals(t)
    return _replace(line, decimals=d) if d else line


def _parse_line(t: str) -> Line:
    _check_unsupported(t)
    continuation = t.startswith("=")
    if continuation:
        t = t[1:]
    is_list = bool(re.search(r",|;|\bor\b|\band\b|±|\+-", t))
    if "=" in t and not is_list and t.count("=") >= 2 or continuation and "=" in t:
        pieces = [p for p in t.split("=")]
        if any(not p.strip() for p in pieces):
            raise Unreadable("empty chain piece")
        if continuation or not (_parse(pieces[0]).free_symbols):
            ok = _chain_consistent(pieces)
            if continuation:
                return Line("expr", (_parse(pieces[-1]),), raw=_parse(pieces[-1], evaluate=False), head=_parse(pieces[0]),
                            internal_slip=not ok, raw_head=_parse(pieces[0], evaluate=False))
            lhs_t = pieces[0]
        elif any(_parse(p).free_symbols for p in pieces[1:-1]):
            # "a+b+c = 18+10+c = 42" or "x+x = 2x = 6": the last "=" states an equation (values were
            # substituted or terms collected first), so the line is pieces[-2] = pieces[-1]
            ok, lhs_t = True, pieces[-2]
        else:
            ok, lhs_t = _chain_consistent(pieces[1:]), pieces[0]
        rhs_t = pieces[-1]
        lhs, rhs = _parse(lhs_t), _parse(rhs_t)
        return Line("eq", (sp.expand(lhs - rhs),), ((_parse(lhs_t, evaluate=False), _parse(rhs_t, evaluate=False)),), internal_slip=not ok)
    if "=" not in t:
        if "±" in t:
            raise Unsupported("±")
        raw = _parse(t, evaluate=False)
        return Line("expr", (_parse(t),), raw=raw)
    pieces = _split_solutions(t) if re.search(r",|;|\bor\b|\band\b|±|\+-", t) else [t]
    exprs, sides = [], []
    for p in pieces:
        if p.count("=") != 1:
            raise Unreadable(f"equation: {p!r}")
        lhs_t, rhs_t = p.split("=")
        lhs, rhs = _parse(lhs_t), _parse(rhs_t)
        exprs.append(sp.expand(lhs - rhs))
        sides.append((_parse(lhs_t, evaluate=False), _parse(rhs_t, evaluate=False)))
    kind = "eq" if len(pieces) == 1 else "sols"
    return Line(kind, tuple(exprs), tuple(sides))


# ---------------------------------------------------------------- equivalence

def _symbols(*lines: Line) -> List[sp.Symbol]:
    syms = set()
    for ln in lines:
        for e in ln.exprs:
            syms |= e.free_symbols
    return sorted(syms, key=lambda s: s.name)


def _num_equal(a: sp.Expr, b: sp.Expr, syms: Sequence[sp.Symbol], rng: random.Random, trials: int = 12) -> bool:
    good = 0
    for _ in range(trials * 3):
        point = {s: sp.Rational(rng.randint(-40, 40), rng.randint(1, 9)) for s in syms}
        try:
            va, vb = complex(sp.N(a.subs(point), 30)), complex(sp.N(b.subs(point), 30))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if any(map(lambda z: z != z or abs(z) == float("inf"), (va, vb))):
            continue
        if abs(va - vb) > 1e-9 * max(1.0, abs(va), abs(vb)):
            return False
        good += 1
        if good >= trials:
            return True
    return good >= 3


def expressions_equivalent(a: sp.Expr, b: sp.Expr) -> bool:
    diff = sp.simplify(a - b)
    if diff == 0:
        return True
    return _num_equal(a, b, sorted(a.free_symbols | b.free_symbols, key=lambda s: s.name), random.Random(7))


def _solution_set(line: Line, var: sp.Symbol):
    sets = []
    for e in line.exprs:
        s = sp.solveset(e, var, domain=sp.S.Reals)
        if isinstance(s, sp.ConditionSet):
            return None
        sets.append(s)
    if line.kind == "sols":
        return sp.Union(*sets)
    return sets[0]


def _sets_equal(s1, s2, tol: float = 1e-9) -> bool:
    if s1 == s2:
        return True
    if isinstance(s1, sp.FiniteSet) and isinstance(s2, sp.FiniteSet):
        v1 = sorted(complex(sp.N(v)).real for v in s1)
        v2 = sorted(complex(sp.N(v)).real for v in s2)
        return len(v1) == len(v2) and all(abs(x - y) <= tol for x, y in zip(v1, v2))
    try:
        return bool(sp.Complement(s1, s2) == sp.EmptySet and sp.Complement(s2, s1) == sp.EmptySet)
    except Exception:
        return False


def _proportional(a: sp.Expr, b: sp.Expr) -> bool:
    if a == 0 or b == 0:
        return a == b
    ratio = sp.simplify(a / b)
    return ratio.is_number and ratio != 0


def equations_equivalent(prev: Line, cur: Line) -> Optional[bool]:
    syms = _symbols(prev, cur)
    if len(syms) == 0:
        # e.g. "0=0" vs "5=5": compare truth values
        tv = lambda ln: all(sp.simplify(e) == 0 for e in ln.exprs)
        return tv(prev) == tv(cur)
    if len(syms) == 1:
        s1, s2 = _solution_set(prev, syms[0]), _solution_set(cur, syms[0])
        if s1 is not None and s2 is not None:
            tol = 0.5 * 10 ** (-cur.decimals) + 1e-9 if cur.decimals else 1e-9
            return _sets_equal(s1, s2, tol)
    if prev.kind == "eq" and cur.kind == "eq":
        return _proportional(prev.exprs[0], cur.exprs[0])
    return None


def is_check_line(line: Line) -> bool:
    """An equation with no unknowns, e.g. "3(5)-5=10" written to check an answer."""
    return line.kind == "eq" and not line.exprs[0].free_symbols


def is_solved(line: Line) -> bool:
    """x = number (or a list of those): the point where a student checks an answer."""
    for lhs, rhs in line.sides:
        if not (isinstance(lhs, sp.Symbol) and not rhs.free_symbols) and not (isinstance(rhs, sp.Symbol) and not lhs.free_symbols):
            return False
    return bool(line.sides) and line.kind in ("eq", "sols")


def check_line_holds(anchor: Line, line: Line) -> Optional[bool]:
    truth = sp.simplify(line.exprs[0]) == 0
    if truth:
        return True
    syms = _symbols(anchor)
    if anchor.kind != "expr" and len(syms) == 1:
        s = _solution_set(anchor, syms[0])
        if s == sp.EmptySet:
            return True  # "3=5" after an equation with no solution is the right conclusion
    return False


def relate(prev: Line, cur: Line) -> Relation:
    if prev.kind == "expr" and cur.kind == "expr":
        head = cur.head if cur.head is not None else cur.exprs[0]
        before, after = prev.exprs[0].free_symbols, head.free_symbols
        if before and after < before and not expressions_equivalent(prev.exprs[0], head):
            cur_raw = cur.raw_head if cur.raw_head is not None else cur.raw
            cur_shape = sp.count_ops(cur_raw if cur_raw is not None else head)
            if cur_shape >= 2:  # numbers written into a structure (e.g. 5((5)^2-3(16))), not a collapse to one number
                return Relation.UNSUPPORTED  # values were substituted into the same shape: new chain
        return Relation.EQUIVALENT if expressions_equivalent(prev.exprs[0], head) else Relation.NOT_EQUIVALENT
    if prev.kind == "expr" or cur.kind == "expr":
        return Relation.UNSUPPORTED
    eq = equations_equivalent(prev, cur)
    if eq is None:
        return Relation.UNSUPPORTED
    return Relation.EQUIVALENT if eq else Relation.NOT_EQUIVALENT


# ---------------------------------------------------------------- hints

def _rebuild(e: sp.Basic) -> sp.Basic:
    if not e.args:
        return e
    return e.func(*[_rebuild(a) for a in e.args])


def _terms(e: sp.Expr) -> List[sp.Expr]:
    return list(e.args) if isinstance(e, sp.Add) else [e]


def _as_eq_line(lhs: sp.Expr, rhs: sp.Expr) -> Line:
    l, r = _rebuild(lhs), _rebuild(rhs)
    return Line("eq", (sp.expand(l - r),), ((lhs, rhs),))


def _as_expr_line(e: sp.Expr) -> Line:
    return Line("expr", (_rebuild(e),), raw=e)


def _replace_term(side: sp.Expr, i: int, new: Optional[sp.Expr]) -> sp.Expr:
    ts = _terms(side)
    ts = ts[:i] + ([new] if new is not None else []) + ts[i + 1:]
    if not ts:
        return sp.Integer(0)
    return sp.Add(*ts, evaluate=False) if len(ts) > 1 else ts[0]


def _variants_sign(prev: Line) -> Iterable[Line]:
    if prev.kind == "eq":
        lhs, rhs = prev.sides[0]
        for side_i, side in enumerate((lhs, rhs)):
            for i, t in enumerate(_terms(side)):
                new_side = _replace_term(side, i, sp.Mul(-1, t, evaluate=False))
                yield _as_eq_line(new_side, rhs) if side_i == 0 else _as_eq_line(lhs, new_side)
    elif prev.kind == "expr" and prev.raw is not None:
        for i, t in enumerate(_terms(prev.raw)):
            yield _as_expr_line(_replace_term(prev.raw, i, sp.Mul(-1, t, evaluate=False)))


def _bad_distributions(e: sp.Expr) -> Iterable[sp.Expr]:
    """Yield copies of e where one c*(a+b+...) is distributed to only one term."""
    if isinstance(e, sp.Mul):
        factors = list(e.args)
        for i, f in enumerate(factors):
            if isinstance(f, sp.Add):
                others = factors[:i] + factors[i + 1:]
                c = sp.Mul(*others, evaluate=False) if len(others) > 1 else (others[0] if others else sp.Integer(1))
                ts = list(f.args)
                for j in range(len(ts)):
                    new_terms = [sp.Mul(c, t, evaluate=False) if k == j else t for k, t in enumerate(ts)]
                    yield sp.Add(*new_terms, evaluate=False)
    for idx, a in enumerate(e.args):
        for sub in _bad_distributions(a):
            args = list(e.args)
            args[idx] = sub
            yield e.func(*args, evaluate=False)


def _sign_distributions(e: sp.Expr) -> Iterable[sp.Expr]:
    """Yield copies of e where c*(a+b+...) was expanded with one product's sign flipped."""
    if isinstance(e, sp.Mul):
        factors = list(e.args)
        for i, f in enumerate(factors):
            if isinstance(f, sp.Add):
                others = factors[:i] + factors[i + 1:]
                c = sp.Mul(*others, evaluate=False) if len(others) > 1 else (others[0] if others else sp.Integer(1))
                ts = list(f.args)
                for j in range(len(ts)):
                    new_terms = [sp.Mul(-1 if k == j else 1, c, t, evaluate=False) for k, t in enumerate(ts)]
                    yield sp.Add(*new_terms, evaluate=False)
    for idx, a in enumerate(e.args):
        for sub in _sign_distributions(a):
            args = list(e.args)
            args[idx] = sub
            yield e.func(*args, evaluate=False)


def _variants_sign_distribution(prev: Line) -> Iterable[Line]:
    if prev.kind == "eq":
        lhs, rhs = prev.sides[0]
        for v in _sign_distributions(lhs):
            yield _as_eq_line(v, rhs)
        for v in _sign_distributions(rhs):
            yield _as_eq_line(lhs, v)
    elif prev.kind == "expr" and prev.raw is not None:
        for v in _sign_distributions(prev.raw):
            yield _as_expr_line(v)


def _negated_solutions(prev: Line, cur: Line) -> bool:
    """Factored form solved with the roots' signs flipped, e.g. (x-7)(x-6)=0 -> x=-7 or x=-6."""
    if cur.kind != "sols" and cur.kind != "eq":
        return False
    syms = _symbols(prev, cur)
    if len(syms) != 1:
        return False
    x = syms[0]
    s1, s2 = _solution_set(prev, x), _solution_set(cur, x)
    if not isinstance(s1, sp.FiniteSet) or not isinstance(s2, sp.FiniteSet) or len(s2) == 0:
        return False
    v1 = {sp.nsimplify(v) for v in s1}
    v2 = [sp.nsimplify(v) for v in s2]
    flipped = sum(1 for v in v2 if -v in v1 and v not in v1)
    return flipped >= 1 and all((v in v1) or (-v in v1) for v in v2)


def _variants_distribution(prev: Line) -> Iterable[Line]:
    if prev.kind == "eq":
        lhs, rhs = prev.sides[0]
        for v in _bad_distributions(lhs):
            yield _as_eq_line(v, rhs)
        for v in _bad_distributions(rhs):
            yield _as_eq_line(lhs, v)
    elif prev.kind == "expr" and prev.raw is not None:
        for v in _bad_distributions(prev.raw):
            yield _as_expr_line(v)


def _variants_dropped(prev: Line) -> Iterable[Line]:
    if prev.kind == "eq":
        lhs, rhs = prev.sides[0]
        for side_i, side in enumerate((lhs, rhs)):
            ts = _terms(side)
            if len(ts) < 2:
                continue
            for i in range(len(ts)):
                new_side = _replace_term(side, i, None)
                yield _as_eq_line(new_side, rhs) if side_i == 0 else _as_eq_line(lhs, new_side)
    elif prev.kind == "expr" and prev.raw is not None:
        ts = _terms(prev.raw)
        if len(ts) >= 2:
            for i in range(len(ts)):
                yield _as_expr_line(_replace_term(prev.raw, i, None))


def _arithmetic_fixable(prev: Line, cur: Line) -> bool:
    """Can changing ONE number in the current line make it follow from the previous one?"""
    k = sp.Symbol("k_fix")
    if cur.kind == "expr" and cur.raw is not None:
        target = cur.raw
        numbers = [a for a in sp.preorder_traversal(target) if isinstance(a, sp.Integer) and a not in (sp.Integer(-1),)]
        for n in set(numbers):
            replaced = target.xreplace({n: k})
            for cand in _solve_for_k_expr(prev.exprs[0], _rebuild(replaced), k):
                if expressions_equivalent(prev.exprs[0], _rebuild(replaced).subs(k, cand)):
                    return True
        return False
    if cur.kind == "eq":
        lhs, rhs = cur.sides[0]
        syms = _symbols(prev)
        if len(syms) != 1:
            return False
        sols = _solution_set(prev, syms[0])
        if not isinstance(sols, sp.FiniteSet) or len(sols) == 0:
            return False
        x0 = list(sols)[0]
        for side_i, side in enumerate((lhs, rhs)):
            numbers = {a for a in sp.preorder_traversal(side) if isinstance(a, sp.Integer) and a not in (sp.Integer(-1),)}
            for n in numbers:
                new_side = side.xreplace({n: k})
                cand_line_l, cand_line_r = (new_side, rhs) if side_i == 0 else (lhs, new_side)
                d = sp.expand(_rebuild(cand_line_l) - _rebuild(cand_line_r))
                try:
                    ks = sp.solve(d.subs(syms[0], x0), k)
                except Exception:
                    continue
                for kv in ks:
                    if not kv.is_real:
                        continue
                    fixed = Line("eq", (sp.expand(d.subs(k, kv)),))
                    if equations_equivalent(prev, fixed):
                        return True
    return False


def _solve_for_k_expr(a: sp.Expr, b_with_k: sp.Expr, k: sp.Symbol) -> List[sp.Expr]:
    syms = sorted((a.free_symbols | b_with_k.free_symbols) - {k}, key=lambda s: s.name)
    point = {s: sp.Rational(7, 3) + i for i, s in enumerate(syms)}
    try:
        return [v for v in sp.solve(sp.Eq(a.subs(point), b_with_k.subs(point)), k) if v.is_real]
    except Exception:
        return []


def _matches_any(variants: Iterable[Line], cur: Line) -> bool:
    for v in variants:
        try:
            if relate(v, cur) == Relation.EQUIVALENT:
                return True
        except Exception:
            continue
    return False


def classify_hint(prev: Line, cur: Line) -> Hint:
    if prev.kind != "expr" and cur.kind != "expr":
        syms = _symbols(prev, cur)
        if len(syms) == 1:
            s1, s2 = _solution_set(prev, syms[0]), _solution_set(cur, syms[0])
            if s1 is not None and s2 is not None and s2 != sp.EmptySet and s1 != s2:
                if sp.Complement(s2, s1) == sp.EmptySet:
                    return Hint.LOST_SOLUTION
                if sp.Complement(s1, s2) == sp.EmptySet:
                    return Hint.EXTRA_SOLUTION
    if _negated_solutions(prev, cur):
        return Hint.SIGN
    if _matches_any(_variants_distribution(prev), cur):
        return Hint.DISTRIBUTION
    if _matches_any(_variants_sign(prev), cur) or _matches_any(_variants_sign_distribution(prev), cur):
        return Hint.SIGN
    if _matches_any(_variants_dropped(prev), cur):
        return Hint.DROPPED_TERM
    try:
        if _arithmetic_fixable(prev, cur):
            return Hint.ARITHMETIC
    except Exception:
        pass
    return Hint.CHECK_STEP


# ---------------------------------------------------------------- culprit (which written term to circle)

def _top_terms(side: str, offset: int) -> List[Tuple[int, int]]:
    """(start, end) spans of top-level additive terms in `side`, sign included, positions in the full text."""
    spans, depth, start = [], 0, 0
    for i, ch in enumerate(side):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch in "+-" and depth == 0 and i > 0 and side[i - 1] not in "^*/(+-":
            if side[start:i].strip():
                spans.append((offset + start, offset + i))
            start = i
    if side[start:].strip():
        spans.append((offset + start, offset + len(side)))
    return spans


def culprit_term(prev_text: str, cur_text: str) -> Optional[str]:
    """The single written term of the slip line that, if it were different, would make the step valid.

    Returns the term as the student wrote it (e.g. "10" in 2x+3=7 -> 2x=10), never the corrected value.
    None when the step is fine, or when no single term explains the slip (then the whole line is circled).
    """
    try:
        prev, cur = parse_line(prev_text), parse_line(cur_text)
        if relate(prev, cur) != Relation.NOT_EQUIVALENT:
            return None
    except Exception:
        return None
    t = normalise(cur_text)
    lead = 1 if t.startswith("=") else 0
    body = t[lead:]
    if body.count("=") > 1:
        return None
    sides = body.split("=")
    spans, off = [], lead
    for sd in sides:
        spans += _top_terms(sd, off)
        off += len(sd) + 1
    k = sp.Symbol("k_fix")
    ranked = sorted(spans, key=lambda s: (not re.fullmatch(r"\s*[+-]?\s*[0-9.]+\s*", t[s[0]:s[1]]), s[0]))
    for a, b in ranked:
        term = t[a:b].strip()
        sign = "-" if term.startswith("-") else "+"
        cand_text = t[:a] + (sign if a > lead and t[a - 1] not in "=(" or sign == "-" else "") + "(k_fix)" + t[b:]
        try:
            cand = parse_line(cand_text.replace("k_fix", "K"))
        except Exception:
            continue
        K = sp.Symbol("K")
        try:
            if cand.kind == "expr" and prev.kind == "expr":
                ks = _solve_for_k_expr(prev.exprs[0], cand.exprs[0] if cand.head is None else cand.head, K)
                ok = any(expressions_equivalent(prev.exprs[0], (cand.exprs[0] if cand.head is None else cand.head).subs(K, v)) for v in ks)
            else:
                syms = sorted(set(_symbols(prev)) - {K}, key=lambda s: s.name)
                if len(syms) != 1:
                    continue
                sols = _solution_set(prev, syms[0])
                if not isinstance(sols, sp.FiniteSet) or len(sols) == 0:
                    continue
                x0 = list(sols)[0]
                ks = [v for v in sp.solve(cand.exprs[0].subs(syms[0], x0), K) if v.is_real]
                ok = any(equations_equivalent(prev, Line("eq", (sp.expand(cand.exprs[0].subs(K, v)),))) for v in ks)
        except Exception:
            continue
        if ok:
            return term.lstrip("+").strip()
    return None
