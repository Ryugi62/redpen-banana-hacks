"""Static UI contract: the page shows the result image first, handles 'not sure' verdicts and never hangs."""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "public")


def read(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


def test_home_shows_an_image_before_any_click():
    html = read("index.html")
    assert 'src="hero.jpg"' in html and os.path.exists(os.path.join(ROOT, "hero.jpg"))


def test_ui_handles_uncertain_lines_and_timeouts():
    js = read("app.js")
    assert "uncertain_lines" in js and "AbortController" in js and "startStages" in js


def test_every_sample_is_a_recorded_model_run():
    js = read("app.js")
    for sid in ("s1", "s2", "s3", "s4"):
        assert f'id: "{sid}"' in js
        data = json.load(open(os.path.join(ROOT, "samples", f"{sid}.result.json")))
        assert data.get("recorded") is True and "no model call" not in data["model"]


def test_hidden_hint_chip_really_hides_and_edits_are_disclosed():
    assert ".chip[hidden]" in read("style.css")
    assert "checked as you typed" in read("app.js")


def test_progress_text_does_not_pretend_to_know_the_server_stage():
    js = read("app.js")
    assert "STAGES" not in js and "WAIT_TEXT" in js
