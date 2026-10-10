"""Verifier-only check on the seeded set (unit-level gate, not the headline metric)."""
import collections
import sys

from eval.seeded import generate
from redpen.domain.model import Step
from redpen.domain.verdict import judge


def run(n=80, verbose=False):
    items = generate(n)
    stats = collections.Counter()
    misses = []
    for it in items:
        v = judge([Step(i, t, 1.0) for i, t in enumerate(it.lines)])
        if it.first_slip is None:
            stats["clean"] += 1
            if v.first_slip is not None:
                stats["false_alarm"] += 1
                misses.append(("FA", it, v))
        else:
            stats["slipped"] += 1
            if v.first_slip == it.first_slip:
                stats["slip_hit"] += 1
                if it.kind and v.hint and v.hint.value == it.kind:
                    stats["hint_hit"] += 1
                if it.kind:
                    stats["hint_total"] += 1
            else:
                misses.append(("MISS", it, v))
    res = {
        "items": len(items),
        "first_slip_accuracy": stats["slip_hit"] / max(1, stats["slipped"]),
        "false_alarm_rate": stats["false_alarm"] / max(1, stats["clean"]),
        "hint_accuracy": stats["hint_hit"] / max(1, stats["hint_total"]),
        "clean": stats["clean"], "slipped": stats["slipped"],
    }
    if verbose:
        for tag, it, v in misses[:25]:
            print(tag, it.template, it.kind, it.first_slip, "->", v.first_slip, [r.value for r in v.relations], it.lines)
    return res


if __name__ == "__main__":
    print(run(verbose="-v" in sys.argv))
