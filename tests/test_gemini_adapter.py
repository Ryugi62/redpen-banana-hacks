"""AC-7: malformed vision output degrades to unreadable lines, never crashes (no network)."""
from redpen.adapters.gemini import parse_free, parse_marked


def test_missing_and_bad_ids_become_unreadable():
    payload = {"lines": [{"id": 1, "text": "2x+3=7", "kind": "math", "confidence": 0.9},
                         {"id": 9, "text": "zzz", "confidence": 1},
                         {"id": "x"}, "garbage",
                         {"id": 3, "text": None, "confidence": "high"}]}
    r = parse_marked(payload, 3)
    assert r[0].text == "2x+3=7" and r[0].confidence == 0.9
    assert r[1].confidence == 0.0
    assert r[2].text == "" and r[2].confidence == 0.0


def test_non_dict_payload():
    assert [x.confidence for x in parse_marked([], 2)] == [0.0, 0.0]
    assert parse_free("nope", (100, 100)) == []


def test_free_mode_boxes_are_scaled_and_sorted():
    payload = {"lines": [{"box_2d": [500, 100, 600, 900], "text": "x=2", "kind": "math", "confidence": 0.8},
                         {"box_2d": [100, 100, 200, 900], "text": "2x=4", "kind": "math", "confidence": 0.9},
                         {"box_2d": [1, 2], "text": "bad"}]}
    res = parse_free(payload, (1000, 2000))
    assert [r.text for _, r in res] == ["2x=4", "x=2"]
    assert res[0][0].y0 == 200 and res[0][0].x1 == 900
