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


@dataclass
class GradeResult:
    steps: List[Step]
    verdict: Verdict
    plan: MarkupPlan
    image_png: bytes
    timings_ms: Dict[str, int] = field(default_factory=dict)
    mode: str = "cv-segmented"
    rechecked: bool = False


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


def confirm_slip(image: bytes, steps: List[Step], reader) -> tuple:
    """Before accusing a line, re-read it and the line it is compared with at higher zoom.

    Returns (steps, rechecked). Misreads that created a fake slip are corrected here.
    """
    reread = getattr(reader, "reread", None)
    if reread is None:
        return steps, False
    v = judge(steps)
    if v.first_slip is None:
        return steps, False
    slip = v.first_slip
    prev = next((i for i in range(slip - 1, -1, -1) if steps[i].kind != "prose" and steps[i].readable), None)
    idx = [i for i in (prev, slip) if i is not None and steps[i].box is not None]
    if not idx:
        return steps, False
    try:
        again = reread(image, [steps[i].box for i in idx])
    except Exception:
        return steps, False
    fixed = list(steps)
    for i, r in zip(idx, again):
        if r.text.strip():
            fixed[i] = replace(steps[i], text=r.text, confidence=max(r.confidence, 0.0) if r.confidence else steps[i].confidence)
    return fixed, True


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
            steps, rechecked = confirm_slip(image, steps, self.locator)
            timings["confirm"] = int((time.perf_counter() - t) * 1000)
            res = _finish(image, steps, self.renderer, timings, mode="model-located")
            res.rechecked = rechecked
            return res
        t = time.perf_counter()
        readings = self.transcriber.transcribe(image, boxes) if boxes else []
        timings["read"] = int((time.perf_counter() - t) * 1000)
        steps = []
        for i, box in enumerate(boxes):
            r = readings[i] if i < len(readings) else Reading("", 0.0)
            steps.append(Step(index=i, text=r.text, confidence=r.confidence, box=box, kind=r.kind))
        t = time.perf_counter()
        steps, rechecked = confirm_slip(image, steps, self.transcriber)
        timings["confirm"] = int((time.perf_counter() - t) * 1000)
        res = _finish(image, steps, self.renderer, timings)
        res.rechecked = rechecked
        return res


class Regrade:
    def __init__(self, renderer: MarkupRenderer):
        self.renderer = renderer

    def execute(self, image: bytes, edits: List[StepEdit]) -> GradeResult:
        steps = [Step(index=i, text=e.text, confidence=e.confidence, box=e.box, kind=e.kind) for i, e in enumerate(edits)]
        return _finish(image, steps, self.renderer, {})
