"""GeminiTranscriber: one vision call per photo.

Set-of-mark mode: the page is sent with numbered boxes drawn on it (from the CV segmenter),
and the model returns a transcription per box id. Free mode (no usable boxes): the model
returns lines with its own box_2d. The model only READS; it never judges correctness.
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from redpen.domain.model import LineBox, Reading

from .imageio import load_rgb

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT_MARKED = """You are a careful transcriber of handwritten school maths. The photo shows a student's work.
Each written line is surrounded by a numbered box (red number at its left).
For EVERY box id, copy exactly what the student wrote in that box, as plain-text maths:
- Use ^ for powers, / for fractions written as a/b, * only if the student wrote a multiplication sign, sqrt( ) for roots.
- Write fractions with a horizontal bar as (numerator)/(denominator).
- COPY MISTAKES EXACTLY. Never correct, simplify, complete or "fix" the student's work, even if it is obviously wrong.
- If a box contains words (instructions, "Given", labels, question text) set kind to "prose" and put the words in text.
- If you cannot read a box reliably, give your best guess and a low confidence.
- confidence: 0.0-1.0, how sure you are that text matches the handwriting character for character.
Return JSON only."""

PROMPT_FREE = """You are a careful transcriber of handwritten school maths. The photo shows a student's work.
List every written line from top to bottom. For each line give box_2d = [ymin, xmin, ymax, xmax] normalised to 0-1000,
and copy exactly what the student wrote, as plain-text maths (^ for powers, (a)/(b) for stacked fractions, sqrt( ) for roots).
COPY MISTAKES EXACTLY - never correct or complete the work. Lines made of words get kind "prose".
confidence: 0.0-1.0, how sure you are the text matches the handwriting character for character. Return JSON only."""

SCHEMA_MARKED = {
    "type": "OBJECT",
    "properties": {
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "INTEGER"},
                    "text": {"type": "STRING"},
                    "kind": {"type": "STRING", "enum": ["math", "prose"]},
                    "confidence": {"type": "NUMBER"},
                },
                "required": ["id", "text", "kind", "confidence"],
            },
        }
    },
    "required": ["lines"],
}

SCHEMA_FREE = {
    "type": "OBJECT",
    "properties": {
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                    "text": {"type": "STRING"},
                    "kind": {"type": "STRING", "enum": ["math", "prose"]},
                    "confidence": {"type": "NUMBER"},
                },
                "required": ["box_2d", "text", "kind", "confidence"],
            },
        }
    },
    "required": ["lines"],
}


class VisionUnavailable(RuntimeError):
    """Quota, network or key problem - the UI offers samples / typing instead."""


def mark_boxes(img: Image.Image, boxes: List[LineBox]) -> Image.Image:
    out = img.copy()
    d = ImageDraw.Draw(out)
    size = max(16, int(min(b.height for b in boxes) * 0.6)) if boxes else 20
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    for i, b in enumerate(boxes, 1):
        d.rectangle([b.x0 - 4, b.y0 - 4, b.x1 + 4, b.y1 + 4], outline=(230, 0, 0), width=3)
        tx = max(0, b.x0 - int(size * 1.3) - 6)
        d.rectangle([tx, b.y0 - 2, tx + int(size * 1.2), b.y0 + size + 2], fill=(230, 0, 0))
        d.text((tx + 3, b.y0), str(i), fill=(255, 255, 255), font=font)
    return out


def _jpeg_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def parse_marked(payload: dict, n: int) -> List[Reading]:
    """Map model output to one Reading per box. Missing / malformed -> unreadable (AC-7)."""
    out = [Reading("", 0.0) for _ in range(n)]
    lines = payload.get("lines") if isinstance(payload, dict) else None
    if not isinstance(lines, list):
        return out
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        try:
            idx = int(ln.get("id")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= idx < n:
            continue
        text = ln.get("text") if isinstance(ln.get("text"), str) else ""
        try:
            conf = float(ln.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        kind = "prose" if ln.get("kind") == "prose" else "math"
        out[idx] = Reading(text.strip(), max(0.0, min(1.0, conf)), kind)
    return out


def parse_free(payload: dict, size: Tuple[int, int]) -> List[Tuple[LineBox, Reading]]:
    W, H = size
    res = []
    for ln in (payload.get("lines") or []) if isinstance(payload, dict) else []:
        try:
            y0, x0, y1, x1 = [int(v) for v in ln["box_2d"]][:4]
        except (KeyError, TypeError, ValueError):
            continue
        box = LineBox(int(x0 * W / 1000), int(y0 * H / 1000), int(x1 * W / 1000), int(y1 * H / 1000))
        if box.width <= 2 or box.height <= 2:
            continue
        text = ln.get("text") if isinstance(ln.get("text"), str) else ""
        try:
            conf = float(ln.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        res.append((box, Reading(text.strip(), max(0.0, min(1.0, conf)), "prose" if ln.get("kind") == "prose" else "math")))
    res.sort(key=lambda t: t[0].y0)
    return res


class GeminiTranscriber:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, timeout: int = 45):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model or os.environ.get("REDPEN_MODEL", "gemini-3.5-flash")
        self.timeout = timeout
        self.last_raw: Optional[str] = None

    def _call(self, prompt: str, img: Image.Image, schema: dict) -> dict:
        if not self.api_key:
            raise VisionUnavailable("no key")
        body = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": _jpeg_b64(img)}}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": schema},
        }
        req = urllib.request.Request(
            ENDPOINT.format(model=self.model), data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise VisionUnavailable(f"HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise VisionUnavailable(str(e)) from e
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            return {}
        self.last_raw = text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    def transcribe(self, image: bytes, boxes: List[LineBox]) -> List[Reading]:
        img = load_rgb(image)
        payload = self._call(PROMPT_MARKED, mark_boxes(img, boxes), SCHEMA_MARKED)
        return parse_marked(payload, len(boxes))

    def locate_and_transcribe(self, image: bytes) -> List[Tuple[LineBox, Reading]]:
        img = load_rgb(image)
        return parse_free(self._call(PROMPT_FREE, img, SCHEMA_FREE), img.size)
