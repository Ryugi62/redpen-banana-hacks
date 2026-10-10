"""RecordedTranscriber: replays known readings (samples, tests, evaluation ground truth)."""
from __future__ import annotations

from typing import List, Sequence

from redpen.domain.model import LineBox, Reading


class RecordedTranscriber:
    model = "recorded"

    def __init__(self, texts: Sequence[str], confidence: float = 1.0):
        self.texts = list(texts)
        self.confidence = confidence

    def transcribe(self, image: bytes, boxes: List[LineBox]) -> List[Reading]:
        return [Reading(t, self.confidence) for t in self.texts[: len(boxes)]]
