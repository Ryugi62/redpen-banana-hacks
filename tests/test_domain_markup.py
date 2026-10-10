"""AC-2 plan shape and slip marks."""
from redpen.domain.model import Step, LineBox, MarkKind
from redpen.domain.verdict import judge
from redpen.domain.markup import plan_markup


def mk(texts):
    return [Step(index=i, text=t, confidence=0.99, box=LineBox(10, 10 + 60 * i, 300, 60 + 60 * i)) for i, t in enumerate(texts)]


def test_all_correct_plan_has_ticks_and_summary():
    s = mk(["2x+3=7", "2x=4", "x=2"])
    plan = plan_markup(s, judge(s))
    kinds = [m.kind for m in plan.marks]
    assert kinds.count(MarkKind.TICK) == 3
    assert kinds.count(MarkKind.SUMMARY) == 1
    assert MarkKind.CIRCLE not in kinds


def test_slip_plan_circles_slip_and_writes_note():
    s = mk(["2x+3=7", "2x=10", "x=5"])
    plan = plan_markup(s, judge(s))
    circles = [m for m in plan.marks if m.kind == MarkKind.CIRCLE]
    notes = [m for m in plan.marks if m.kind == MarkKind.NOTE]
    assert len(circles) == 1 and circles[0].step == 1
    assert len(notes) == 1 and notes[0].step == 1 and notes[0].text
    ticks = [m.step for m in plan.marks if m.kind == MarkKind.TICK]
    assert ticks == [0]  # nothing after the slip is ticked
    assert "5" not in notes[0].text and "2" not in notes[0].text  # never leaks numbers/answers


def test_unreadable_gets_query_mark():
    s = mk(["2x+3=7", "2x=4", "x=2"])
    s[1] = Step(index=1, text="2x=4", confidence=0.1, box=s[1].box)
    plan = plan_markup(s, judge(s))
    assert [m.step for m in plan.marks if m.kind == MarkKind.QUERY] == [1]


def test_edited_lines_get_no_tick_on_the_original_ink():
    """Round-2 judges: after a fix, RedPen ticked the student's ORIGINAL wrong ink."""
    from redpen.domain.model import Step as S
    s = mk(["3x-5=10", "3x=15", "x=5"])
    s[1] = S(index=1, text="3x=15", confidence=1.0, box=s[1].box, edited=True)
    s[2] = S(index=2, text="x=5", confidence=1.0, box=s[2].box, edited=True)
    plan = plan_markup(s, judge(s))
    ticks = [m.step for m in plan.marks if m.kind == MarkKind.TICK]
    assert ticks == [0]
    notes = {m.step: m.text for m in plan.marks if m.kind == MarkKind.NOTE}
    assert notes == {1: "typed 3x=15", 2: "typed x=5"}
    summary = [m for m in plan.marks if m.kind == MarkKind.SUMMARY][0]
    assert "typed" in summary.text
