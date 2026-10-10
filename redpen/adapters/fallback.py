"""Try several vision models in order (free-tier quotas are per model)."""
from __future__ import annotations

from typing import List

from redpen.domain.model import LineBox, Reading

from .gemini import VisionUnavailable


class FallbackTranscriber:
    def __init__(self, transcribers: list):
        self.transcribers = transcribers
        self.used: str = ""

    def _try(self, fn_name: str, *args):
        errors = []
        for t in self.transcribers:
            try:
                out = getattr(t, fn_name)(*args)
                self.used = getattr(t, "model", type(t).__name__)
                return out
            except VisionUnavailable as e:
                errors.append(f"{getattr(t, 'model', '?')}: {e}")
        raise VisionUnavailable("; ".join(errors) or "no transcriber")

    def transcribe(self, image: bytes, boxes: List[LineBox]) -> List[Reading]:
        return self._try("transcribe", image, boxes)

    def reread(self, image: bytes, boxes: List[LineBox]) -> List[Reading]:
        return self._try("reread", image, boxes)

    def locate_and_transcribe(self, image: bytes):
        return self._try("locate_and_transcribe", image)
