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


# --- hedged requests: a slow model must not hold the student for 25 s ---
import threading
import time


class Slow:
    def __init__(self, name, delay, text="slow"):
        self.model, self.delay, self.text, self.calls = name, delay, text, 0

    def transcribe(self, image, boxes):
        self.calls += 1
        time.sleep(self.delay)
        return [Reading(self.text, 0.9)]


def test_hedge_starts_backup_when_primary_is_slow():
    slow, fast = Slow("slow", 1.5), Slow("fast", 0.0, "x=2")
    f = FallbackTranscriber([slow, fast], hedge_after=0.1)
    t = time.perf_counter()
    out = f.transcribe(b"", [])
    assert time.perf_counter() - t < 0.8
    assert out[0].text == "x=2" and f.used == "fast"


def test_hedge_does_not_spend_backup_quota_when_primary_is_fast():
    first, backup = Slow("first", 0.0, "x=1"), Slow("backup", 0.0)
    f = FallbackTranscriber([first, backup], hedge_after=0.5)
    assert f.transcribe(b"", [])[0].text == "x=1"
    time.sleep(0.05)
    assert backup.calls == 0


def test_hedge_failure_moves_on_without_waiting():
    fast = Slow("fast", 0.0, "x=3")
    f = FallbackTranscriber([Busy(), fast], hedge_after=5.0)
    t = time.perf_counter()
    assert f.transcribe(b"", [])[0].text == "x=3"
    assert time.perf_counter() - t < 1.0


def test_hedge_all_busy_raises():
    with pytest.raises(VisionUnavailable):
        FallbackTranscriber([Busy(), Busy()], hedge_after=0.1).transcribe(b"", [])


def test_deadline_bounds_the_whole_chain():
    f = FallbackTranscriber([Slow("a", 2.0), Slow("b", 2.0), Slow("c", 2.0)], hedge_after=0.1, deadline_s=0.5)
    t = time.perf_counter()
    with pytest.raises(VisionUnavailable):
        f.transcribe(b"", [])
    assert time.perf_counter() - t < 1.0
