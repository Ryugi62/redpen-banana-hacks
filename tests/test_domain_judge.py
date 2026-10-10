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
