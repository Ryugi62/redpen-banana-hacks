"""Ubiquitous language of RedPen (see SPEC.md section 3). Pure data, no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

READABLE_CONFIDENCE = 0.6


@dataclass(frozen=True)
class LineBox:
    """Rectangle around one written line, in page pixels (x0, y0) top-left, (x1, y1) bottom-right."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def iou(self, other: "LineBox") -> float:
        ix0, iy0 = max(self.x0, other.x0), max(self.y0, other.y0)
        ix1, iy1 = min(self.x1, other.x1), min(self.y1, other.y1)
        inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
        union = self.width * self.height + other.width * other.height - inter
        return inter / union if union > 0 else 0.0


@dataclass(frozen=True)
class Reading:
    """Transcription of one LineBox. kind = "math" or "prose" (words, labels, question text)."""

    text: str
    confidence: float
    kind: str = "math"


@dataclass(frozen=True)
class Step:
    """One line of the student's work."""

    index: int
    text: str
    confidence: float = 1.0
    box: Optional[LineBox] = None
    kind: str = "math"

    @property
    def readable(self) -> bool:
        return self.confidence >= READABLE_CONFIDENCE and bool(self.text.strip())


class Relation(str, Enum):
    START = "start"
    EQUIVALENT = "equivalent"
    NOT_EQUIVALENT = "not_equivalent"
    UNREADABLE = "unreadable"
    UNSUPPORTED = "unsupported"
    PROSE = "prose"


class Hint(str, Enum):
    SIGN = "sign"
    ARITHMETIC = "arithmetic"
    DISTRIBUTION = "distribution"
    DROPPED_TERM = "dropped_term"
    LOST_SOLUTION = "lost_solution"
    EXTRA_SOLUTION = "extra_solution"
    CHECK_STEP = "check_step"


HINT_NOTES = {
    Hint.SIGN: "check the sign",
    Hint.ARITHMETIC: "recheck arithmetic",
    Hint.DISTRIBUTION: "distribute to every term",
    Hint.DROPPED_TERM: "a term went missing",
    Hint.LOST_SOLUTION: "lost a solution",
    Hint.EXTRA_SOLUTION: "extra solution",
    Hint.CHECK_STEP: "check this step",
}

HINT_EXPLANATIONS = {
    Hint.SIGN: "A term crossed the equals sign (or was negated) without its sign flipping.",
    Hint.ARITHMETIC: "The structure is right, but one number was computed wrong.",
    Hint.DISTRIBUTION: "A factor was multiplied into only part of the brackets.",
    Hint.DROPPED_TERM: "A term from the previous line disappeared.",
    Hint.LOST_SOLUTION: "This line has fewer solutions than the previous one. Did you divide by something that can be zero?",
    Hint.EXTRA_SOLUTION: "This line allows a value the previous line did not (e.g. one that makes a denominator zero).",
    Hint.CHECK_STEP: "This line does not follow from the previous one.",
}


@dataclass(frozen=True)
class Verdict:
    relations: List[Relation]
    first_slip: Optional[int]
    hint: Optional[Hint]

    @property
    def held(self) -> int:
        """Number of steps verified before the first slip (or overall if none)."""
        end = self.first_slip if self.first_slip is not None else len(self.relations)
        return sum(1 for r in self.relations[:end] if r in (Relation.START, Relation.EQUIVALENT))


class MarkKind(str, Enum):
    TICK = "tick"
    CIRCLE = "circle"
    NOTE = "note"
    QUERY = "query"
    SUMMARY = "summary"


@dataclass(frozen=True)
class Mark:
    kind: MarkKind
    step: Optional[int]
    text: str = ""


@dataclass(frozen=True)
class MarkupPlan:
    marks: Tuple[Mark, ...] = field(default_factory=tuple)
