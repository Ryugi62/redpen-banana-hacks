"""Composition root + JSON contract used by the HTTP handlers (and tests)."""
from __future__ import annotations

import base64
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict, List

from redpen.adapters.fallback import FallbackTranscriber
from redpen.adapters.gemini import GeminiTranscriber, VisionUnavailable
from redpen.adapters.imageio import normalise_bytes
from redpen.adapters.orient import upright_bytes
from redpen.adapters.renderer import InkRenderer
from redpen.adapters.segmenter import ProjectionSegmenter
from redpen.application.grade import GradePage, GradeResult, Regrade, StepEdit
from redpen.domain.model import HINT_EXPLANATIONS, LineBox

DEFAULT_MODELS = "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-2.5-flash,gemini-3.6-flash,gemini-3.7-flash,gemma-4-31b-it"
MAX_IMAGE_BYTES = 4_000_000
RATE_PER_HOUR = 12

_hits: Dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


class BadRequest(ValueError):
    pass


class RateLimited(RuntimeError):
    pass


def allow(client: str, now: float | None = None) -> bool:
    now = now or time.time()
    with _lock:
        q = _hits[client]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= RATE_PER_HOUR:
            return False
        q.append(now)
        return True


def build_transcriber():
    models = [m.strip() for m in os.environ.get("REDPEN_MODELS", DEFAULT_MODELS).split(",") if m.strip()]
    return FallbackTranscriber([GeminiTranscriber(model=m, timeout=40 if "gemma" in m else 25) for m in models])


def _decode_image(payload: Dict[str, Any]) -> bytes:
    data = payload.get("image")
    if not isinstance(data, str) or not data:
        raise BadRequest("image (base64) is required")
    if data.startswith("data:"):
        data = data.split(",", 1)[-1]
    try:
        raw = base64.b64decode(data, validate=False)
    except Exception as e:
        raise BadRequest("image is not base64") from e
    if len(raw) > MAX_IMAGE_BYTES:
        raise BadRequest("image too large (max 4 MB)")
    try:
        return upright_bytes(normalise_bytes(raw))
    except Exception as e:
        raise BadRequest("could not decode image") from e


def to_json(res: GradeResult, model: str = "") -> Dict[str, Any]:
    v = res.verdict
    steps = []
    for s, rel in zip(res.steps, v.relations):
        steps.append({
            "index": s.index, "text": s.text, "confidence": round(s.confidence, 2), "kind": s.kind,
            "box": [s.box.x0, s.box.y0, s.box.x1, s.box.y1] if s.box else None, "relation": rel.value,
        })
    maths = [r for r in v.relations if r.value != "prose"]
    return {
        "steps": steps,
        "verdict": {
            "first_slip": v.first_slip,
            "first_slip_line": (v.first_slip + 1) if v.first_slip is not None else None,
            "hint": v.hint.value if v.hint else None,
            "explanation": HINT_EXPLANATIONS.get(v.hint) if v.hint else None,
            "held": v.held,
            "checked": sum(1 for r in maths if r.value in ("start", "equivalent")),
            "maths_lines": len(maths),
        },
        "image": "data:image/png;base64," + base64.b64encode(res.image_png).decode(),
        "mode": res.mode,
        "rechecked": res.rechecked,
        "model": model,
        "timings_ms": res.timings_ms,
    }


def grade(payload: Dict[str, Any], client: str = "anon") -> Dict[str, Any]:
    image = _decode_image(payload)
    if not allow(client):
        raise RateLimited("Too many photos this hour - try a sample or edit the lines instead.")
    tr = build_transcriber()
    t = time.perf_counter()
    res = GradePage(ProjectionSegmenter(), tr, InkRenderer(), locator=tr).execute(image)
    out = to_json(res, tr.used)
    out["timings_ms"]["total"] = int((time.perf_counter() - t) * 1000)
    return out


def regrade(payload: Dict[str, Any]) -> Dict[str, Any]:
    image = _decode_image(payload)
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps or len(raw_steps) > 40:
        raise BadRequest("steps must be a non-empty list (max 40)")
    edits: List[StepEdit] = []
    for s in raw_steps:
        if not isinstance(s, dict):
            raise BadRequest("each step must be an object")
        text = str(s.get("text", ""))[:200]
        box = s.get("box")
        lb = LineBox(*[int(v) for v in box[:4]]) if isinstance(box, list) and len(box) >= 4 else None
        kind = "prose" if s.get("kind") == "prose" else "math"
        edits.append(StepEdit(text, lb, 1.0, kind))
    res = Regrade(InkRenderer()).execute(image, edits)
    return to_json(res, "none (no model call)")


__all__ = ["grade", "regrade", "BadRequest", "RateLimited", "VisionUnavailable", "allow"]
