"""AC-1..AC-4, AC-6: verdict and hints (pure domain)."""
import pytest

from redpen.domain.model import Step, Relation, Hint
from redpen.domain.verdict import judge


def steps(*texts, conf=None):
    conf = conf or {}
    return [Step(index=i, text=t, confidence=conf.get(i, 0.99)) for i, t in enumerate(texts)]


def test_ac1_first_slip_and_carried_error():
    v = judge(steps("2x+3=7", "2x=10", "x=5"))
    assert v.first_slip == 1
    assert v.relations[1] == Relation.NOT_EQUIVALENT
    assert v.relations[2] == Relation.EQUIVALENT
    assert v.hint == Hint.SIGN  # +3 moved across without flipping its sign


def test_arithmetic_slip():
    v = judge(steps("2x+3=7", "2x=5", "x=5/2"))
    assert v.first_slip == 1 and v.hint == Hint.ARITHMETIC


def test_ac2_all_correct():
    v = judge(steps("2x+3=7", "2x=4", "x=2"))
    assert v.first_slip is None
    assert v.relations == [Relation.START, Relation.EQUIVALENT, Relation.EQUIVALENT]


def test_ac3_unreadable_is_skipped():
    v = judge(steps("2x+3=7", "2x=4", "x=2", conf={1: 0.2}))
    assert v.relations[1] == Relation.UNREADABLE
    assert v.relations[2] == Relation.EQUIVALENT  # compared with step 0
    assert v.first_slip is None


def test_ac3_unparseable_text_is_unreadable():
    v = judge(steps("2x+3=7", "2x=)(4", "x=2"))
    assert v.relations[1] == Relation.UNREADABLE
    assert v.first_slip is None


def test_ac4_unsupported():
    v = judge(steps("integral(x, x)=x^2/2", "x=1"))
    assert Relation.NOT_EQUIVALENT not in v.relations
    assert v.relations[0] == Relation.UNSUPPORTED


@pytest.mark.parametrize("a,b", [
    ("2(x+3)", "2x+6"), ("(x+1)^2", "x^2+2x+1"), ("x^2-9", "(x-3)(x+3)"),
    ("(2x+4)/2", "x+2"), ("3x-x", "2x"), ("6x/3", "2x"), ("x*x", "x^2"),
])
def test_expression_equivalent(a, b):
    assert judge(steps(a, b)).relations[1] == Relation.EQUIVALENT


@pytest.mark.parametrize("a,b", [
    ("2(x+3)", "2x+3"), ("(x+1)^2", "x^2+1"), ("x^2-9", "(x-9)(x+1)"), ("3x-x", "3"),
])
def test_expression_not_equivalent(a, b):
    assert judge(steps(a, b)).relations[1] == Relation.NOT_EQUIVALENT


@pytest.mark.parametrize("a,b", [
    ("x^2-5x+6=0", "(x-2)(x-3)=0"), ("(x-2)(x-3)=0", "x=2 or x=3"), ("(x-2)(x-3)=0", "x=2, x=3"),
    ("x/2=3", "x=6"), ("5=x+1", "x=4"), ("2x+3=3+2x", "0=0"),
])
def test_equation_equivalent(a, b):
    assert judge(steps(a, b)).relations[1] == Relation.EQUIVALENT


@pytest.mark.parametrize("a,b,hint", [
    ("3x-5=10", "3x=5", Hint.SIGN),
    ("2(x+3)=10", "2x+3=10", Hint.DISTRIBUTION),
    ("x^2=3x", "x=3", Hint.LOST_SOLUTION),
    ("4x=12", "x=4", Hint.ARITHMETIC),
    ("x+2=5", "x=7", Hint.SIGN),
])
def test_ac6_hints(a, b, hint):
    v = judge(steps(a, b))
    assert v.first_slip == 1
    assert v.hint == hint


def test_unicode_and_spacing_normalised():
    v = judge(steps("2·x − 4 = 6", "2x = 10", "x = 5"))
    assert v.first_slip is None


def test_chained_equalities_are_checked_inside_the_line():
    v = judge(steps("c = 42 - 18 = 24", "c = 24"))
    assert v.first_slip is None
    v = judge(steps("18 + c = 42", "c = 42 - 18 = 23"))
    assert v.first_slip == 1


def test_wrong_arithmetic_inside_one_line_is_a_slip():
    v = judge(steps("P(1) = 2 + 5 - 5 - 2 = 1"))
    assert v.first_slip == 0


def test_prose_lines_are_ignored_and_keep_the_chain():
    s = [Step(0, "2x+3=7", 0.99), Step(1, "subtract 3", 0.99, kind="prose"), Step(2, "2x=4", 0.99)]
    v = judge(s)
    assert v.relations[1] == Relation.PROSE
    assert v.relations[2] == Relation.EQUIVALENT


def test_units_are_ignored():
    assert judge(steps("a + 10 = 28", "a = 18 cm")).first_slip is None


def test_substituting_values_starts_a_new_chain_not_a_slip():
    v = judge(steps("a^3+b^3+c^3-3abc", "=(a+b+c)((a+b+c)^2-3(ab+bc+ca))", "=5((5)^2-3(16))", "=5(-23)", "=-115"))
    assert v.first_slip is None
    v = judge(steps("=5((5)^2-3(16))", "=5(-4)"))
    assert v.first_slip == 1


# --- found by mock judges 2026-10-10 20:3x -------------------------------------------------

def test_true_answer_check_line_is_not_a_slip():
    v = judge(steps("3x-5=10", "3x=15", "x=5", "3(5)-5=10"))
    assert v.first_slip is None
    assert v.relations[3] == Relation.EQUIVALENT
    v = judge(steps("2x+3=7", "x=2", "2(2)+3=7", "7=7"))
    assert v.first_slip is None


def test_false_answer_check_line_is_an_arithmetic_slip():
    v = judge(steps("2x+3=7", "x=2", "2(2)+3=8"))
    assert v.first_slip == 2 and v.hint == Hint.ARITHMETIC


def test_contradiction_after_no_solution_equation_is_correct():
    v = judge(steps("2x+3=2x+5", "3=5"))
    assert v.first_slip is None


def test_lines_after_a_check_still_compare_with_the_last_equation():
    v = judge(steps("2x+3=7", "x=2", "2(2)+3=7", "x=3"))
    assert v.first_slip == 3


@pytest.mark.parametrize("a,b", [("3x=1", "x=0.33"), ("3x=1", "x=0.333"), ("x^2=2", "x=1.41 or x=-1.41"), ("7x=22", "x=3.14")])
def test_rounded_decimals_are_accepted(a, b):
    assert judge(steps(a, b)).first_slip is None


@pytest.mark.parametrize("a,b", [("3x=1", "x=0.5"), ("3x=1", "x=0.31"), ("x^2=2", "x=1.5 or x=-1.5")])
def test_wrong_decimals_are_still_slips(a, b):
    assert judge(steps(a, b)).first_slip == 1


def test_doubtful_line_is_not_accused_and_breaks_the_chain():
    s = steps("5(x+9)=40", "5x+45=80", "5x=35", "x=7")
    s[0] = Step(index=0, text="5(x+9)=40", confidence=0.99, doubtful=True)
    v = judge(s)
    assert v.relations[0] == Relation.UNREADABLE
    assert v.relations[1] == Relation.START
    assert v.first_slip is None


@pytest.mark.parametrize("text", ["9^9^9=x", "2^999999=x", "x=" + "9" * 40])
def test_pathological_input_returns_fast(text):
    import time
    t = time.perf_counter()
    v = judge(steps("x=1", text))
    assert time.perf_counter() - t < 2.0
    assert v.relations[1] in (Relation.UNSUPPORTED, Relation.UNREADABLE)


# --- round-2 mock judges: common student notation -------------------------------------------

@pytest.mark.parametrize("prefix", ["=> ", "⇒", "∴ ", "→", "-> ", "therefore "])
def test_leading_arrows_and_therefore_are_ignored(prefix):
    v = judge(steps("2x+3=7", prefix + "2x=10", "x=5"))
    assert v.first_slip == 1 and v.hint == Hint.SIGN


@pytest.mark.parametrize("sep", [" v ", " V ", " or "])
def test_v_between_solutions_means_or(sep):
    v = judge(steps("x^2+4x+3=0", "(x+1)(x+3)=0", "x=-1" + sep + "x=-3"))
    assert v.first_slip is None


@pytest.mark.parametrize("suffix", ["//", " //", " ■", " ✓", " #"])
def test_trailing_end_marks_are_ignored(suffix):
    v = judge(steps("2x+3=7", "2x=4", "x=2" + suffix))
    assert v.first_slip is None and v.relations[2] == Relation.EQUIVALENT


def test_true_numeric_line_counts_as_a_check_only_after_a_solved_line():
    v = judge(steps("2x=4", "0=0"))
    assert v.first_slip == 1  # 2x=4 does not turn into 0=0


def test_angle_sign_is_part_of_the_name():
    v = judge(steps("90+2∠B=180", "2∠B=90", "∠B=45"))
    assert v.first_slip is None and v.relations[2] == Relation.EQUIVALENT
    assert judge(steps("90+2∠B=180", "2∠B=90", "∠B=50")).first_slip == 2


# --- culprit: which written part of the slip line is wrong (to circle the term, not the whole line) ---
from redpen.domain.algebra import culprit_term  # noqa: E402


@pytest.mark.parametrize("prev,cur,want", [
    ("2x+3=7", "2x=10", "10"),
    ("3x-5=10", "3x=5", "5"),
    ("4(x-2)=2x+6", "4x-2=2x+6", "-2"),
    ("2x+3=7", "2x=5", "5"),
    ("5(x+1)+2(x-2)", "5x+5+2x-4", None),  # correct: no culprit
])
def test_culprit_term(prev, cur, want):
    assert culprit_term(prev, cur) == want


def test_culprit_term_never_contains_the_fix():
    # it names what the student wrote, not what it should be
    assert culprit_term("2x+3=7", "2x=10") == "10"


def test_verdict_carries_the_culprit_term():
    v = judge(steps("2x+3=7", "2x=10", "x=5"))
    assert v.first_slip == 1 and v.culprit == "10"


def test_substitution_chain_ending_in_a_given_value_is_an_equation():
    # real answer sheet (held-out crop 01): a=18, b=10 substituted, "= 42" is the given total
    v = judge(steps("a+b+c=18+10+c=42", "18+c=42", "c=42-18=24"))
    assert v.first_slip == 1
    v = judge(steps("x+x=2x=6", "x=3"))
    assert v.first_slip is None
