"""Use cases: UC-1 GradePage, UC-2 Regrade (no vision call)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from redpen.domain.markup import plan_markup
from redpen.domain.model import LineBox, MarkupPlan, Reading, Step, Verdict
from redpen.domain.verdict import judge

from .ports import LineSegmenter, MarkupRenderer, Transcriber


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


def _finish(image: bytes, steps: List[Step], renderer: MarkupRenderer, timings: Dict[str, int]) -> GradeResult:
    t = time.perf_counter()
    verdict = judge(steps)
    plan = plan_markup(steps, verdict)
    timings["verify"] = int((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    png = renderer.render(image, steps, plan)
    timings["render"] = int((time.perf_counter() - t) * 1000)
    return GradeResult(steps, verdict, plan, png, timings)


class GradePage:
    def __init__(self, segmenter: LineSegmenter, transcriber: Transcriber, renderer: MarkupRenderer):
        self.segmenter, self.transcriber, self.renderer = segmenter, transcriber, renderer

    def execute(self, image: bytes) -> GradeResult:
        timings: Dict[str, int] = {}
        t = time.perf_counter()
        boxes = self.segmenter.segment(image)
        timings["segment"] = int((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        readings = self.transcriber.transcribe(image, boxes) if boxes else []
        timings["read"] = int((time.perf_counter() - t) * 1000)
        steps = []
        for i, box in enumerate(boxes):
            r = readings[i] if i < len(readings) else Reading("", 0.0)
            steps.append(Step(index=i, text=r.text, confidence=r.confidence, box=box, kind=r.kind))
        return _finish(image, steps, self.renderer, timings)


class Regrade:
    def __init__(self, renderer: MarkupRenderer):
        self.renderer = renderer

    def execute(self, image: bytes, edits: List[StepEdit]) -> GradeResult:
        steps = [Step(index=i, text=e.text, confidence=e.confidence, box=e.box, kind=e.kind) for i, e in enumerate(edits)]
        return _finish(image, steps, self.renderer, {})
