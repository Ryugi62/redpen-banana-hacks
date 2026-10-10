"""Ports the application needs from the outside world."""
from __future__ import annotations

from typing import List, Protocol, Tuple

from redpen.domain.model import LineBox, MarkupPlan, Reading, Step


class LineSegmenter(Protocol):
    def segment(self, image: bytes) -> List[LineBox]: ...


class Transcriber(Protocol):
    def transcribe(self, image: bytes, boxes: List[LineBox]) -> List[Reading]: ...


class MarkupRenderer(Protocol):
    def render(self, image: bytes, steps: List[Step], plan: MarkupPlan) -> bytes: ...


class LineLocator(Protocol):
    """Fallback when classical segmentation is implausible: the model finds and reads lines."""

    def locate_and_transcribe(self, image: bytes) -> List[Tuple[LineBox, Reading]]: ...
