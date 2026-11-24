from math_func import classify_number


def test_classify_number_all_branches_negative_zero_even_odd() -> None:
    """Covers all branches of classify_number: negative, zero, even, odd."""
    assert classify_number(-5) == "negative"
    assert classify_number(0) == "zero"
    assert classify_number(4) == "positive-even"
    assert classify_number(7) == "positive-odd"


def test_classify_number_partial_negative_and_even() -> None:
    """This test covers some branches of classify_number: negative and even."""
    assert classify_number(-1) == "negative"
    assert classify_number(2) == "positive-even"


def test_classify_number_remaining_zero_and_odd() -> None:
    """Covers the remaining branches of classify_number: zero and odd."""
    assert classify_number(0) == "zero"
    assert classify_number(3) == "positive-odd"
