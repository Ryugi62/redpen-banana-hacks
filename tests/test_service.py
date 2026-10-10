"""HTTP contract (no network): regrade end-to-end through real adapters, input validation."""
import base64
import io

import pytest
from PIL import Image

from redpen.infrastructure import service


def b64_page():
    img = Image.new("RGB", (600, 300), (250, 250, 245))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def test_regrade_contract():
    out = service.regrade({"image": b64_page(), "steps": [
        {"text": "2x+3=7", "box": [20, 20, 200, 60]},
        {"text": "2x=10", "box": [20, 100, 200, 140]},
        {"text": "x=5", "box": [20, 180, 200, 220]}]})
    assert out["verdict"]["first_slip_line"] == 2
    assert out["verdict"]["hint"] == "sign"
    assert out["image"].startswith("data:image/png;base64,")
    assert [s["relation"] for s in out["steps"]] == ["start", "not_equivalent", "equivalent"]


def test_bad_inputs():
    with pytest.raises(service.BadRequest):
        service.regrade({"image": "", "steps": []})
    with pytest.raises(service.BadRequest):
        service.regrade({"image": b64_page(), "steps": "x"})
    with pytest.raises(service.BadRequest):
        service.grade({"image": base64.b64encode(b"not an image").decode()})


def test_rate_limit():
    for _ in range(service.RATE_PER_HOUR):
        assert service.allow("t1", now=1000.0)
    assert not service.allow("t1", now=1001.0)
    assert service.allow("t1", now=1000.0 + 3601)
