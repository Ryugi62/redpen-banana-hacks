"""Use cases: UC-1 GradePage, UC-2 Regrade (no vision call)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from redpen.domain.markup import plan_markup
from redpen.domain.model import LineBox, MarkupPlan, Reading, Step, Verdict
from redpen.domain.verdict import judge

from .ports import LineLocator, LineSegmenter, MarkupRenderer, Transcriber


@dataclass(frozen=True)
class StepEdit:
    text: str
    box: Optional[LineBox]
    confidence: float = 1.0
    kind: str = "math"
    edited: bool = False


@dataclass
class GradeResult:
    steps: List[Step]
    verdict: Verdict
    plan: MarkupPlan
    image_png: bytes
    timings_ms: Dict[str, int] = field(default_factory=dict)
    mode: str = "cv-segmented"
    rechecked: bool = False
    uncertain: List[int] = field(default_factory=list)


def plausible_lines(boxes: List[LineBox], page: Optional[tuple]) -> bool:
    """Classical segmentation is trusted only if it looks like lines of handwriting."""
    if not boxes or len(boxes) > 30:
        return False
    if page:
        _, h = page
        if any(b.height > 0.28 * h for b in boxes):
            return False
    return True


def _finish(image: bytes, steps: List[Step], renderer: MarkupRenderer, timings: Dict[str, int], mode: str = "cv-segmented") -> GradeResult:
    t = time.perf_counter()
    verdict = judge(steps)
    plan = plan_markup(steps, verdict)
    timings["verify"] = int((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    png = renderer.render(image, steps, plan)
    timings["render"] = int((time.perf_counter() - t) * 1000)
    return GradeResult(steps, verdict, plan, png, timings, mode)


def _same_reading(a: str, b: str) -> bool:
    norm = lambda t: t.replace(" ", "").replace("*", "").lower()
    return norm(a) == norm(b)


def confirm_slip(image: bytes, steps: List[Step], reader) -> tuple:
    """Before accusing a line, read it and the line it is compared with a second time, zoomed in.

    Two readings that agree (or that both break at the same line) -> the slip stands.
    Readings that disagree about whether this line breaks -> the changed lines are marked doubtful:
    RedPen asks the student to check them instead of accusing (a misread must never look like a mistake,
    and a "corrected" re-read must never silently erase a real one).
    Returns (steps, rechecked, uncertain_indices).
    """
    reread = getattr(reader, "reread", None)
    if reread is None:
        return steps, False, []
    v1 = judge(steps)
    if v1.first_slip is None:
        return steps, False, []
    slip = v1.first_slip
    prev = next((i for i in range(slip - 1, -1, -1) if steps[i].kind != "prose" and steps[i].readable), None)
    idx = [i for i in (prev, slip) if i is not None and steps[i].box is not None]
    if not idx:
        return steps, False, []
    try:
        again = reread(image, [steps[i].box for i in idx])
    except Exception:
        return steps, False, []
    second = list(steps)
    changed = []
    for i, r in zip(idx, again):
        if r.text.strip() and not _same_reading(r.text, steps[i].text):
            second[i] = replace(steps[i], text=r.text)
            changed.append(i)
    if not changed or judge(second).first_slip == slip:
        return steps, True, []
    marked = list(steps)
    for i in changed:
        marked[i] = replace(steps[i], doubtful=True)
    return marked, True, changed


class GradePage:
    def __init__(self, segmenter: LineSegmenter, transcriber: Transcriber, renderer: MarkupRenderer, locator: Optional[LineLocator] = None):
        self.segmenter, self.transcriber, self.renderer, self.locator = segmenter, transcriber, renderer, locator

    def execute(self, image: bytes) -> GradeResult:
        timings: Dict[str, int] = {}
        t = time.perf_counter()
        boxes = self.segmenter.segment(image)
        page = self.segmenter.page_size(image) if hasattr(self.segmenter, "page_size") else None
        timings["segment"] = int((time.perf_counter() - t) * 1000)
        if self.locator is not None and not plausible_lines(boxes, page):
            t = time.perf_counter()
            located = self.locator.locate_and_transcribe(image)
            timings["read"] = int((time.perf_counter() - t) * 1000)
            steps = [Step(index=i, text=r.text, confidence=r.confidence, box=b, kind=r.kind) for i, (b, r) in enumerate(located)]
            t = time.perf_counter()
            steps, rechecked, uncertain = confirm_slip(image, steps, self.locator)
            timings["confirm"] = int((time.perf_counter() - t) * 1000)
            res = _finish(image, steps, self.renderer, timings, mode="model-located")
            res.rechecked, res.uncertain = rechecked, uncertain
            return res
        t = time.perf_counter()
        readings = self.transcriber.transcribe(image, boxes) if boxes else []
        timings["read"] = int((time.perf_counter() - t) * 1000)
        steps = []
        for i, box in enumerate(boxes):
            r = readings[i] if i < len(readings) else Reading("", 0.0)
            steps.append(Step(index=i, text=r.text, confidence=r.confidence, box=box, kind=r.kind))
        t = time.perf_counter()
        steps, rechecked, uncertain = confirm_slip(image, steps, self.transcriber)
        timings["confirm"] = int((time.perf_counter() - t) * 1000)
        res = _finish(image, steps, self.renderer, timings)
        res.rechecked, res.uncertain = rechecked, uncertain
        return res


class Regrade:
    def __init__(self, renderer: MarkupRenderer):
        self.renderer = renderer

    def execute(self, image: bytes, edits: List[StepEdit]) -> GradeResult:
        steps = [Step(index=i, text=e.text, confidence=e.confidence, box=e.box, kind=e.kind, edited=e.edited) for i, e in enumerate(edits)]
        return _finish(image, steps, self.renderer, {})
