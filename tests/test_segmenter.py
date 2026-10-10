"""AC-8: line segmentation on synthetic handwritten pages."""
from eval.seeded import generate
from eval.synth import render_page
from redpen.adapters.segmenter import ProjectionSegmenter


def match_rate(n=24):
    seg = ProjectionSegmenter()
    items = generate(10)[:: max(1, 50 // n)][:n]
    hit = total = extra = 0
    for i, it in enumerate(items):
        img, gt = render_page(it.lines, seed=100 + i)
        found = seg.segment(img)
        for g in gt:
            total += 1
            if any(g.iou(f) >= 0.5 for f in found):
                hit += 1
        extra += max(0, len(found) - len(gt))
    return hit / total, extra


def test_ac8_segmentation_iou():
    rate, extra = match_rate()
    assert rate >= 0.9, rate
    assert extra <= 3
