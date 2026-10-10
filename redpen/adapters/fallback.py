"""Try several vision models in order (free-tier quotas are per model).

With ``hedge_after`` set, a model that has not answered after that many seconds gets a
backup request on the next model in parallel; the first good answer wins. A model that
fails (quota, timeout) hands over immediately. Backups are only spent when needed.
"""
from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import List, Optional

from redpen.domain.model import LineBox, Reading

from .gemini import VisionUnavailable


class FallbackTranscriber:
    def __init__(self, transcribers: list, hedge_after: Optional[float] = None, deadline_s: Optional[float] = None):
        self.transcribers = transcribers
        self.hedge_after = hedge_after
        self.deadline_s = deadline_s  # per call; keeps the whole request inside the platform's time limit
        self.used: str = ""

    def _name(self, t) -> str:
        return getattr(t, "model", type(t).__name__)

    def _try(self, fn_name: str, *args):
        if not self.hedge_after:
            return self._sequential(fn_name, *args)
        return self._hedged(fn_name, *args)

    def _sequential(self, fn_name: str, *args):
        errors = []
        for t in self.transcribers:
            try:
                out = getattr(t, fn_name)(*args)
                self.used = self._name(t)
                return out
            except VisionUnavailable as e:
                errors.append(f"{self._name(t)}: {e}")
        raise VisionUnavailable("; ".join(errors) or "no transcriber")

    def _hedged(self, fn_name: str, *args):
        ts = self.transcribers
        if not ts:
            raise VisionUnavailable("no transcriber")
        pool = ThreadPoolExecutor(max_workers=len(ts))
        pending = {}
        errors: List[str] = []
        nxt = 0

        def launch():
            nonlocal nxt
            t = ts[nxt]
            nxt += 1
            pending[pool.submit(getattr(t, fn_name), *args)] = t

        end = time.monotonic() + self.deadline_s if self.deadline_s else None
        try:
            launch()
            while pending:
                more = nxt < len(ts)
                timeout = self.hedge_after if more else None
                if end is not None:
                    left = end - time.monotonic()
                    if left <= 0:
                        raise VisionUnavailable("deadline: " + ("; ".join(errors) or "models too slow"))
                    timeout = min(timeout, left) if timeout is not None else left
                done, _ = wait(list(pending), timeout=timeout, return_when=FIRST_COMPLETED)
                if not done:
                    if more and (end is None or time.monotonic() < end):
                        launch()  # everyone running is slow: add a backup
                    continue
                for fut in done:
                    t = pending.pop(fut)
                    try:
                        out = fut.result()
                    except VisionUnavailable as e:
                        errors.append(f"{self._name(t)}: {e}")
                        continue
                    self.used = self._name(t)
                    return out
                if nxt < len(ts):  # a failure hands over at once
                    launch()
            raise VisionUnavailable("; ".join(errors) or "no transcriber")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def transcribe(self, image: bytes, boxes: List[LineBox]) -> List[Reading]:
        return self._try("transcribe", image, boxes)

    def reread(self, image: bytes, boxes: List[LineBox]) -> List[Reading]:
        return self._try("reread", image, boxes)

    def locate_term(self, image: bytes, box: LineBox, term: str):
        """One short try on the model that just read the page; a miss only means the whole line is circled."""
        t = next((t for t in self.transcribers if self._name(t) == self.used), self.transcribers[0] if self.transcribers else None)
        if t is None or not hasattr(t, "locate_term"):
            return None
        old = getattr(t, "timeout", None)
        try:
            if old is not None:
                t.timeout = min(old, 10)
            return t.locate_term(image, box, term)
        finally:
            if old is not None:
                t.timeout = old

    def locate_and_transcribe(self, image: bytes):
        return self._try("locate_and_transcribe", image)
