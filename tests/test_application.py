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
