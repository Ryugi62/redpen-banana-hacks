"""AC-10: verifier meets S1 on the seeded set (CI gate)."""
from eval.verifier_eval import run


def test_seeded_set_gate():
    res = run(n=40)
    assert res["items"] == 200
    assert res["first_slip_accuracy"] >= 0.95
    assert res["false_alarm_rate"] <= 0.02
