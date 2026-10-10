"""plan_markup: what a teacher's red pen would write, anchored to steps. No drawing here."""
from __future__ import annotations

from typing import List

from .model import HINT_NOTES, Mark, MarkKind, MarkupPlan, Relation, Step, Verdict


def plan_markup(steps: List[Step], verdict: Verdict) -> MarkupPlan:
    marks: List[Mark] = []
    for i, rel in enumerate(verdict.relations):
        if verdict.first_slip is not None and i > verdict.first_slip:
            break  # a teacher stops ticking after the first slip
        if i == verdict.first_slip:
            marks.append(Mark(MarkKind.CIRCLE, i))
            marks.append(Mark(MarkKind.NOTE, i, HINT_NOTES[verdict.hint] if verdict.hint else "check this step"))
        elif rel in (Relation.START, Relation.EQUIVALENT):
            if not steps[i].edited:  # never tick ink that is not what was checked
                marks.append(Mark(MarkKind.TICK, i))
        elif rel == Relation.UNREADABLE:
            marks.append(Mark(MarkKind.QUERY, i))
    if verdict.first_slip is None:
        checked = sum(1 for r in verdict.relations if r in (Relation.START, Relation.EQUIVALENT))
        maths = sum(1 for r in verdict.relations if r != Relation.PROSE)
        if checked == maths and maths:
            typed = any(s.edited for s in steps)
            marks.append(Mark(MarkKind.SUMMARY, None, "checks out as typed" if typed else "all steps check out"))
        else:
            marks.append(Mark(MarkKind.SUMMARY, None, f"{checked} of {maths} checked"))
    return MarkupPlan(tuple(marks))
