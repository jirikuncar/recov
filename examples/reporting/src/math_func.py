"""Small sample module with two functions that contain branching logic.

Functions:
- classify_number(n: int) -> str: returns one of 'negative', 'zero', 'positive-even', 'positive-odd'
- fizzbuzz_tag(n: int) -> str: returns 'fizzbuzz' / 'fizz' / 'buzz' / str(n)
"""

def classify_number(n: int) -> str:
    """Classify an integer by sign and parity.

    Branches:
    - n < 0 -> 'negative'
    - n == 0 -> 'zero'
    - else: parity -> 'positive-even' or 'positive-odd'
    """
    if n < 0:
        return "negative"
    if n == 0:
        return "zero"

    # positive
    if n % 2 == 0:
        return "positive-even"
    return "positive-odd"


def fizzbuzz_tag(n: int) -> str:
    """Return classic fizzbuzz tags. Branching on divisibility by 3 and 5.

    Branches:
    - divisible by 15 -> 'fizzbuzz'
    - divisible by 3 -> 'fizz'
    - divisible by 5 -> 'buzz'
    - else -> string of the number
    """
    if n % 15 == 0:
        return "fizzbuzz"
    if n % 3 == 0:
        return "fizz"
    if n % 5 == 0:
        return "buzz"
    return str(n)
