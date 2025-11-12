from recov import format_and_display_results
from coverage.numbits import nums_to_numbits


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
