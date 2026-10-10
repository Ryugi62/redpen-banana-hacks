from tools.results_table import correct_base, correct_pipe, mcnemar_p, wilson


def test_scoring_rules_match_eval_run():
    assert correct_pipe({"gt": None, "pred_flagged": False, "pred_line": None})
    assert not correct_pipe({"gt": 2, "pred_flagged": True, "pred_line": 1})
    assert correct_base({"gt": 1, "baseline": 2})  # baseline lines are 1-based
    assert correct_base({"gt": None, "baseline": 0})


def test_mcnemar_and_wilson():
    rows = [{"gt": None, "pred_flagged": False, "pred_line": None, "baseline": 3}] * 8
    p, b, c = mcnemar_p(rows)
    assert (b, c) == (8, 0) and abs(p - 2 / 256) < 1e-12
    lo, hi = wilson(5, 10)
    assert 0.23 < lo < 0.24 and 0.76 < hi < 0.77


def test_answer_leak_detector():
    from eval.answer_leak import mentions
    assert mentions("dividing 30 by 6 should result in 5, not 180", [5])
    assert mentions("so x = 5", [5]) and mentions("the answer should be 5.", [5])
    assert not mentions("line 3 is wrong; check 15/3", [5])
    assert not mentions("x = 50", [5])
    assert not mentions("Line 5 is wrong", [5])  # a line number is not the answer
    assert not mentions("The whole solution is correct", [5])


def test_strict_detector_ignores_decimals_that_merely_start_with_the_value():
    from eval.answer_leak import mentions
    assert not mentions("x = 5.5", [5])
