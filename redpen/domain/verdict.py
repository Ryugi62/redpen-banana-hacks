"""judge(steps) -> Verdict.  FirstSlip = first step that does not follow from the last readable step."""
from __future__ import annotations

from typing import List, Optional

from .algebra import Line, Unreadable, culprit_term, Unsupported, check_line_holds, classify_hint, is_check_line, is_solved, parse_line, relate
from .model import Hint, Relation, Step, Verdict


def _parse(step: Step):
    if step.kind == "prose":
        return Relation.PROSE, None
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
    anchor_i: Optional[int] = None
    culprit: Optional[str] = None

    for i, step in enumerate(steps):
        if step.doubtful and step.kind != "prose":
            relations.append(Relation.UNREADABLE)
            anchor = None  # what came before cannot be trusted to judge what comes after
            continue
        failed, line = _parse(step)
        if failed is not None:
            relations.append(failed)
            if failed == Relation.PROSE:
                continue
            if failed == Relation.UNSUPPORTED:
                anchor = None  # cannot reason across an unsupported line
            continue
        if line.internal_slip:
            relations.append(Relation.NOT_EQUIVALENT)
            if first_slip is None:
                first_slip, hint = i, Hint.ARITHMETIC
            anchor, anchor_i = line, i
            continue
        if anchor is None:
            relations.append(Relation.START)
            anchor, anchor_i = line, i
            continue
        if is_check_line(line) and is_solved(anchor):
            # numbers substituted back in to check an answer: true -> fine, false -> arithmetic slip;
            # the chain keeps comparing with the last real equation
            try:
                holds = check_line_holds(anchor, line)
            except Exception:
                holds = None
            if holds is None:
                relations.append(Relation.UNSUPPORTED)
            elif holds:
                relations.append(Relation.EQUIVALENT)
            else:
                relations.append(Relation.NOT_EQUIVALENT)
                if first_slip is None:
                    first_slip, hint = i, Hint.ARITHMETIC
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
            if anchor_i is not None:
                culprit = culprit_term(steps[anchor_i].text, step.text)
        if rel == Relation.UNSUPPORTED:
            # e.g. jumping from an expression to an equation: start a new chain here
            relations[-1] = Relation.START
        anchor, anchor_i = line, i
    return Verdict(relations=relations, first_slip=first_slip, hint=hint, culprit=culprit)
