"""UC-1/UC-2 with fake ports (AC-5)."""
from redpen.application.grade import GradePage, Regrade, StepEdit
from redpen.domain.model import LineBox, Reading


class FakeSegmenter:
    def segment(self, image):
        return [LineBox(0, 0, 100, 40), LineBox(0, 50, 100, 90), LineBox(0, 100, 100, 140)]


class FakeTranscriber:
    def __init__(self, texts):
        self.texts, self.calls = texts, 0

    def transcribe(self, image, boxes):
        self.calls += 1
        return [Reading(t, 0.95) for t in self.texts]


class FakeRenderer:
    def __init__(self):
        self.last = None

    def render(self, image, steps, plan):
        self.last = (steps, plan)
        return b"PNG" + image


def test_grade_page_runs_pipeline_and_keeps_boxes():
    tr = FakeTranscriber(["2x+3=7", "2x=10", "x=5"])
    res = GradePage(FakeSegmenter(), tr, FakeRenderer()).execute(b"img")
    assert tr.calls == 1
    assert res.verdict.first_slip == 1
    assert res.steps[1].box == LineBox(0, 50, 100, 90)
    assert res.image_png == b"PNGimg"


def test_regrade_never_calls_transcriber():
    tr = FakeTranscriber(["2x+3=7", "2x=10", "x=5"])
    renderer = FakeRenderer()
    edits = [StepEdit("2x+3=7", LineBox(0, 0, 100, 40)), StepEdit("2x=4", LineBox(0, 50, 100, 90)), StepEdit("x=2", LineBox(0, 100, 100, 140))]
    res = Regrade(renderer).execute(b"img", edits)
    assert tr.calls == 0
    assert res.verdict.first_slip is None
    assert renderer.last is not None


def test_fewer_readings_than_boxes_marks_missing_lines_unreadable():
    tr = FakeTranscriber(["2x+3=7"])
    res = GradePage(FakeSegmenter(), tr, FakeRenderer()).execute(b"img")
    assert len(res.steps) == 3
    assert [s.readable for s in res.steps] == [True, False, False]


class FakeLocator(FakeTranscriber):
    def locate_and_transcribe(self, image):
        self.calls += 1
        return [(LineBox(0, 0, 100, 40), Reading("2x=4", 0.9)), (LineBox(0, 50, 100, 90), Reading("x=2", 0.9))]


class OneGiantBox:
    def segment(self, image):
        return [LineBox(0, 0, 1000, 900)]

    def page_size(self, image):
        return (1000, 1000)


def test_implausible_segmentation_falls_back_to_model_located_lines():
    loc = FakeLocator([])
    res = GradePage(OneGiantBox(), loc, FakeRenderer(), locator=loc).execute(b"img")
    assert loc.calls == 1
    assert [s.text for s in res.steps] == ["2x=4", "x=2"]
    assert res.verdict.first_slip is None
    assert res.mode == "model-located"


class MisreadThenZoom(FakeTranscriber):
    """First pass misreads line 1 (80 -> 40); the zoomed re-read gets it right."""

    def __init__(self):
        super().__init__(["5(x+9)=40", "5x+45=80", "5x=35", "x=7"])
        self.rereads = 0

    def reread(self, image, boxes):
        self.rereads += 1
        return [Reading("5(x+9)=80", 0.95), Reading("5x+45=80", 0.95)]


class FourLines:
    def segment(self, image):
        return [LineBox(0, 50 * i, 100, 50 * i + 40) for i in range(4)]


def test_slip_is_confirmed_by_zoomed_reread_before_accusing():
    """Two readings disagree about line 1 -> RedPen does not accuse; it asks (query mark) instead."""
    tr = MisreadThenZoom()
    res = GradePage(FourLines(), tr, FakeRenderer()).execute(b"img")
    assert tr.rereads == 1
    assert res.verdict.first_slip is None
    assert res.steps[0].doubtful is True
    assert res.uncertain == [0]
    assert res.rechecked is True


def test_reread_that_erases_a_real_slip_does_not_win_silently():
    """real02 case: the student really wrote 5(-4); the zoomed re-read 'corrects' it to 5(-5)."""
    class Corrector(FakeTranscriber):
        def reread(self, image, boxes):
            return [Reading("5((5)^2-3(10))", 0.95), Reading("=5(-5)", 0.95)]
    tr = Corrector(["5((5)^2-3(10))", "=5(-4)", "=-20"])
    res = GradePage(FakeSegmenter(), tr, FakeRenderer()).execute(b"img")
    assert res.uncertain == [1]
    assert res.steps[1].text == "=5(-4)"  # the first reading is kept and shown, not overwritten
    assert res.verdict.first_slip is None


def test_slip_is_kept_when_both_readings_break_at_the_same_line():
    class Agree(FakeTranscriber):
        def reread(self, image, boxes):
            return [Reading("2x+3=7", 0.95), Reading("2x=11", 0.95)]
    tr = Agree(["2x+3=7", "2x=10", "x=5"])
    res = GradePage(FakeSegmenter(), tr, FakeRenderer()).execute(b"img")
    assert res.verdict.first_slip == 1
    assert res.uncertain == []


def test_genuine_slip_survives_reread():
    class Genuine(FakeTranscriber):
        def reread(self, image, boxes):
            return [Reading("2x+3=7", 0.95), Reading("2x=10", 0.95)]
    tr = Genuine(["2x+3=7", "2x=10", "x=5"])
    res = GradePage(FakeSegmenter(), tr, FakeRenderer()).execute(b"img")
    assert res.verdict.first_slip == 1


class TermLocator(FakeTranscriber):
    def __init__(self, texts, result):
        super().__init__(texts)
        self.result, self.asked = result, []

    def reread(self, image, boxes):
        return [Reading(t, 0.95) for t in ("2x+3=7", "2x=10")]

    def locate_term(self, image, box, term):
        self.asked.append(term)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_circle_goes_round_the_wrong_term_when_vision_finds_it():
    from redpen.domain.model import MarkKind
    tr = TermLocator(["2x+3=7", "2x=10", "x=5"], LineBox(60, 52, 95, 88))
    res = GradePage(FakeSegmenter(), tr, FakeRenderer()).execute(b"img")
    assert tr.asked == ["10"]
    circle = [m for m in res.plan.marks if m.kind == MarkKind.CIRCLE][0]
    assert circle.box == LineBox(60, 52, 95, 88)


def test_whole_line_is_circled_when_the_term_cannot_be_found():
    from redpen.domain.model import MarkKind
    tr = TermLocator(["2x+3=7", "2x=10", "x=5"], RuntimeError("no"))
    res = GradePage(FakeSegmenter(), tr, FakeRenderer()).execute(b"img")
    circle = [m for m in res.plan.marks if m.kind == MarkKind.CIRCLE][0]
    assert circle.box is None and res.verdict.first_slip == 1


def test_term_box_outside_the_line_is_ignored():
    from redpen.domain.model import MarkKind
    tr = TermLocator(["2x+3=7", "2x=10", "x=5"], LineBox(0, 300, 50, 340))
    res = GradePage(FakeSegmenter(), tr, FakeRenderer()).execute(b"img")
    circle = [m for m in res.plan.marks if m.kind == MarkKind.CIRCLE][0]
    assert circle.box is None
