from coverage.numbits import nums_to_numbits

from recov import format_and_display_results, warn_if_contexts_look_lossy


def test_formatting_demo():
    # Minimal mock data for demonstration
    test_results = [
        {
            "test": "test_unique",
            "lines_overlap": 50.00,
            "arcs_overlap": 0.00,
            "is_redundant": False,
            "total_covered_items": 10,
            "source_lines": {"src/recov/foo.py": nums_to_numbits([1, 2])},
            "source_arcs": set(),
        },
        {
            "test": "test_redundant",
            "lines_overlap": 100.00,
            "arcs_overlap": 100.00,
            "is_redundant": True,
            "total_covered_items": 5,
            "source_lines": {"src/recov/foo.py": nums_to_numbits([3])},
            "source_arcs": set(),
        },
    ]
    test_coverage = {
        "test_unique": {
            "lines": {"src/recov/foo.py": nums_to_numbits([1, 2])},
            "arcs": set(),
        },
        "test_redundant": {
            "lines": {"src/recov/foo.py": nums_to_numbits([3])},
            "arcs": set(),
        },
    }
    source_files = {"src/recov/foo.py"}
    format_and_display_results(
        test_results,
        test_coverage,
        source_files,
        with_branches=False,
        verbose=False,
    )


def _result(test, lines):
    return {
        "test": test,
        "lines_overlap": 0.0,
        "arcs_overlap": 0.0,
        "is_redundant": False,
        "total_covered_items": len(lines),
        "source_lines": {"src/recov/foo.py": nums_to_numbits(lines)},
        "source_arcs": set(),
    }


def test_lossy_hint_when_no_line_is_shared(capsys):
    """Zero sharing across many tests is the sysmon signature -- say so."""
    warn_if_contexts_look_lossy([_result("test_a", [1, 2]), _result("test_b", [3, 4])])
    assert "sysmon" in capsys.readouterr().out


def test_no_lossy_hint_when_tests_share_lines(capsys):
    warn_if_contexts_look_lossy([_result("test_a", [1, 2]), _result("test_b", [2, 3])])
    assert capsys.readouterr().out == ""


def test_no_lossy_hint_for_a_single_test(capsys):
    warn_if_contexts_look_lossy([_result("test_a", [1, 2])])
    assert capsys.readouterr().out == ""


def test_no_lossy_hint_without_coverage(capsys):
    warn_if_contexts_look_lossy(
        [
            {**_result("test_a", []), "source_lines": {}},
            {**_result("test_b", []), "source_lines": {}},
        ]
    )
    assert capsys.readouterr().out == ""
