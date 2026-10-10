"""judge(steps) -> Verdict.  FirstSlip = first step that does not follow from the last readable step."""
from __future__ import annotations

from typing import List, Optional

from .algebra import Line, Unreadable, Unsupported, classify_hint, parse_line, relate
from .model import Hint, Relation, Step, Verdict


def _parse(step: Step):
    if not step.readable:
        return Relation.UNREADABLE, None
    try:
        return None, parse_line(step.text)
    except Unsupported:
        return Relation.UNSUPPORTED, None
    except Unreadable:
        return Relation.UNREADABLE, None


def judge(steps: List[Step]) -> Verdict:
    relations: List[Relation] = []
    first_slip: Optional[int] = None
    hint: Optional[Hint] = None
    anchor: Optional[Line] = None  # last readable, supported line

    for i, step in enumerate(steps):
        failed, line = _parse(step)
        if failed is not None:
            relations.append(failed)
            if failed == Relation.UNSUPPORTED:
                anchor = None  # cannot reason across an unsupported line
            continue
        if anchor is None:
            relations.append(Relation.START)
            anchor = line
            continue
        try:
            rel = relate(anchor, line)
        except Exception:
            rel = Relation.UNSUPPORTED
        relations.append(rel)
        if rel == Relation.NOT_EQUIVALENT and first_slip is None:
            first_slip = i
            try:
                hint = classify_hint(anchor, line)
            except Exception:
                hint = Hint.CHECK_STEP
        if rel == Relation.UNSUPPORTED:
            # e.g. jumping from an expression to an equation: start a new chain here
            relations[-1] = Relation.START
        anchor = line
    return Verdict(relations=relations, first_slip=first_slip, hint=hint)
