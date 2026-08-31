"""Tests for the redundancy analysis itself."""

import pytest
from coverage.numbits import nums_to_numbits

from recov import GLOBAL_CONTEXT, analysis_context, calculate_redundancy_analysis, parse_phases

ONE = "src/one.py"
TWO = "src/two.py"
SOURCE_FILES = {ONE, TWO}


def cov(lines=None, arcs=()):
    return {
        "lines": {file: nums_to_numbits(sorted(nums)) for file, nums in (lines or {}).items()},
        "arcs": set(arcs),
    }


def verdicts(test_coverage, **kwargs):
    results = calculate_redundancy_analysis(test_coverage, SOURCE_FILES, False, **kwargs)
    return {result["test"]: result["is_redundant"] for result in results}


def test_tests_covering_the_same_lines_are_redundant():
    """A file only some tests touch must still union across all of them.

    Regression test: the prefix/suffix unions used to drop a file at every
    context that did not cover it, so two tests covering identical lines both
    came out UNIQUE as soon as a third test touched a different file.
    """
    assert verdicts(
        {
            "test_a": cov({ONE: [2, 3]}),
            "test_b": cov({TWO: [2, 3]}),
            "test_c": cov({ONE: [2, 3]}),
        }
    ) == {"test_a": True, "test_b": False, "test_c": True}


def test_a_test_with_a_line_of_its_own_is_unique():
    assert verdicts(
        {
            "test_a": cov({ONE: [2, 3]}),
            "test_b": cov({TWO: [2, 3]}),
            "test_c": cov({ONE: [2, 3, 4]}),
        }
    ) == {"test_a": True, "test_b": False, "test_c": False}


def test_arcs_union_across_files_too():
    results = calculate_redundancy_analysis(
        {
            "test_a": cov({ONE: [2, 3]}, [(ONE, 2, 3)]),
            "test_b": cov({TWO: [2, 3]}, [(TWO, 2, 3)]),
            "test_c": cov({ONE: [2, 3]}, [(ONE, 2, 3)]),
        },
        SOURCE_FILES,
        True,
    )
    assert {r["test"]: r["is_redundant"] for r in results} == {
        "test_a": True,
        "test_b": False,
        "test_c": True,
    }


def test_baseline_coverage_counts_as_covered():
    """Lines covered at import time are still covered once a test is deleted."""
    test_coverage = {
        GLOBAL_CONTEXT: cov({ONE: [5]}),
        "test_a": cov({ONE: [5]}),
        "test_b": cov({ONE: [9]}),
    }
    assert verdicts(test_coverage) == {"test_a": True, "test_b": False}
    assert verdicts(test_coverage, use_baseline=False) == {"test_a": False, "test_b": False}


def test_baseline_arcs_count_as_covered():
    test_coverage = {
        GLOBAL_CONTEXT: cov({ONE: [5]}, [(ONE, 4, 5)]),
        "test_a": cov({ONE: [5]}, [(ONE, 4, 5)]),
        "test_b": cov({ONE: [9]}, [(ONE, 8, 9)]),
    }
    results = calculate_redundancy_analysis(test_coverage, SOURCE_FILES, True)
    assert {r["test"]: r["is_redundant"] for r in results} == {"test_a": True, "test_b": False}


def test_a_test_covering_nothing_is_redundant():
    assert verdicts({"test_a": cov({ONE: [2]}), "test_b": cov()}) == {
        "test_a": False,
        "test_b": True,
    }


# -- phase selection --------------------------------------------------------


def test_analysis_context_keeps_selected_phases():
    nodeid = "tests/t.py::test_a"
    assert analysis_context(f"{nodeid}|run", 1, {"run"}) == nodeid
    assert analysis_context(f"{nodeid}|setup", 1, {"run"}) == GLOBAL_CONTEXT
    assert analysis_context(f"{nodeid}|teardown", 1, {"run"}) == GLOBAL_CONTEXT


def test_analysis_context_keeps_every_phase_by_default():
    nodeid = "tests/t.py::test_a"
    assert analysis_context(f"{nodeid}|setup", 1) == nodeid


def test_analysis_context_keeps_contexts_without_a_phase():
    """There is nothing to filter on, so never drop them."""
    assert analysis_context("tests/t.py::test_a", 1, {"run"}) == "tests/t.py::test_a"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("run", {"run"}),
        ("run,teardown", {"run", "teardown"}),
        (" run , setup ", {"run", "setup"}),
    ],
)
def test_parse_phases(value, expected):
    assert parse_phases(value) == expected


@pytest.mark.parametrize("value", ["", "call", "run,call", ","])
def test_parse_phases_rejects_unknown_values(value):
    with pytest.raises(Exception, match="subset"):
        parse_phases(value)
