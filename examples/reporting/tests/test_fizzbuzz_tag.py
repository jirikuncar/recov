from math_func import fizzbuzz_tag


def test_fizzbuzz_tag_all_branches() -> None:
    """Fully exercise fizzbuzz_tag: fizzbuzz, fizz, buzz, and default."""
    assert fizzbuzz_tag(30) == "fizzbuzz"
    assert fizzbuzz_tag(9) == "fizz"
    assert fizzbuzz_tag(10) == "buzz"
    assert fizzbuzz_tag(7) == "7"


def test_fizzbuzz_tag_only_fizz_branch() -> None:
    """Covers a single branch of fizzbuzz_tag (divisible by 3)."""
    assert fizzbuzz_tag(3) == "fizz"
