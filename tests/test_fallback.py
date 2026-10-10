import pytest

from redpen.adapters.fallback import FallbackTranscriber
from redpen.adapters.gemini import VisionUnavailable
from redpen.domain.model import Reading


class Busy:
    model = "busy"

    def transcribe(self, image, boxes):
        raise VisionUnavailable("HTTP 429")


class Ok:
    model = "ok"

    def transcribe(self, image, boxes):
        return [Reading("x=1", 0.9)]


def test_falls_through_to_next_model():
    f = FallbackTranscriber([Busy(), Ok()])
    assert f.transcribe(b"", [])[0].text == "x=1"
    assert f.used == "ok"


def test_all_busy_raises():
    with pytest.raises(VisionUnavailable):
        FallbackTranscriber([Busy(), Busy()]).transcribe(b"", [])
