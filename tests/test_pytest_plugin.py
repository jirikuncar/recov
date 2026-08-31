"""End-to-end tests: does a single process record every test that runs a line?

These run pytest in a subprocess against a tiny generated project, because the
thing under test is what a real coverage run writes into ``.coverage``.
"""

import os
import subprocess
import sys

import pytest
from coverage.numbits import numbits_to_nums

from recov import GLOBAL_CONTEXT, extract_coverage_data
from recov.contexts import FRAME_SEPARATOR, display_context

US = FRAME_SEPARATOR

SOURCE = """
def shared(x):
    return x + 1


def only_in_a():
    return "a"
"""

TEST_A = """
from lib import shared, only_in_a


def test_a():
    assert shared(1) == 2
    assert only_in_a() == "a"
"""

TEST_B = """
from lib import shared


def test_b():
    assert shared(2) == 3
"""

CONFTEST = """
import pytest
from lib import only_in_a


@pytest.fixture
def prepared():
    return only_in_a()
"""

TEST_D = """
def test_d(prepared):
    assert prepared == "a"
"""

TEST_C = """
import pytest
from lib import shared, only_in_a


@pytest.mark.recov_context("group")
def test_c(recov_context):
    with recov_context("first"):
        assert shared(3) == 4
    with recov_context("second"):
        assert only_in_a() == "a"
"""


@pytest.fixture
def project(tmp_path):
    """Three tests executing ``shared()``, plus one that only uses a fixture."""
    (tmp_path / "lib.py").write_text(SOURCE)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text(TEST_A)
    (tests / "test_b.py").write_text(TEST_B)
    (tests / "test_c.py").write_text(TEST_C)
    (tests / "conftest.py").write_text(CONFTEST)
    (tests / "test_d.py").write_text(TEST_D)
    return tmp_path


def run_pytest(project, *args, env_extra=None):
    env = {
        k: v
        for k, v in os.environ.items()
        # Do not leak the outer run's coverage into the subprocess.
        if not k.startswith(("COV_CORE", "COVERAGE_"))
    }
    env["PYTHONPATH"] = str(project)
    env.update(env_extra or {})
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-p",
            "no:cacheprovider",
            "--cov=lib",
            "--cov-report=",
            *args,
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def lines_by_context(monkeypatch, project, *, context_depth=1, phases=None):
    """Lines of ``lib.py`` per context, including contexts that covered none."""
    monkeypatch.chdir(project)
    test_coverage, source_files, _has_branches = extract_coverage_data(
        with_branches=False, context_depth=context_depth, phases=phases
    )
    lib = next(path for path in source_files if path.endswith("lib.py"))
    return {
        ctx: set(numbits_to_nums(data["lines"].get(lib, b"")))
        for ctx, data in test_coverage.items()
        if ctx != GLOBAL_CONTEXT
    }


SHARED_LINE = 3  # the body of shared()
ONLY_LINE = 7  # the body of only_in_a()

sysmon_only = pytest.mark.skipif(
    not hasattr(sys, "monitoring"),
    reason="sys.monitoring (and so coverage's sysmon core) is not available",
)


def test_every_test_that_runs_a_line_is_recorded(project, monkeypatch):
    """The whole point: one process, and all three tests are credited."""
    result = run_pytest(project, "--recov-context=test")
    assert result.returncode == 0, result.stdout + result.stderr

    covered = lines_by_context(monkeypatch, project)
    runners = {ctx for ctx, lines in covered.items() if SHARED_LINE in lines}
    assert runners == {
        "tests/test_a.py::test_a",
        "tests/test_b.py::test_b",
        "tests/test_c.py::test_c",
    }


def test_nested_contexts_are_recorded_and_roll_up(project, monkeypatch):
    result = run_pytest(project, "--recov-context=test")
    assert result.returncode == 0, result.stdout + result.stderr

    leaves = lines_by_context(monkeypatch, project, context_depth=0)
    assert f"tests/test_c.py::test_c{US}group{US}first" in leaves
    assert f"tests/test_c.py::test_c{US}group{US}second" in leaves

    # Depth 2 rolls both sub-contexts up into the marker's group...
    groups = lines_by_context(monkeypatch, project, context_depth=2)
    group = groups[f"tests/test_c.py::test_c{US}group"]
    # ...and depth 1 rolls them all the way up into the test itself.
    tests = lines_by_context(monkeypatch, project, context_depth=1)
    assert tests["tests/test_c.py::test_c"] == group
    assert group == (
        leaves[f"tests/test_c.py::test_c{US}group{US}first"]
        | leaves[f"tests/test_c.py::test_c{US}group{US}second"]
    )
    assert display_context(f"tests/test_c.py::test_c{US}group") == "tests/test_c.py::test_c ▸ group"


def test_takes_over_from_pytest_cov_contexts(project, monkeypatch):
    """--cov-context=test alongside --recov-context=test must not clobber the stack."""
    result = run_pytest(project, "--cov-context=test", "--recov-context=test")
    assert result.returncode == 0, result.stdout + result.stderr

    leaves = lines_by_context(monkeypatch, project, context_depth=0)
    assert f"tests/test_c.py::test_c{US}group{US}first" in leaves
    runners = {
        ctx for ctx, lines in lines_by_context(monkeypatch, project).items() if SHARED_LINE in lines
    }
    assert len(runners) == 3


def test_phases_run_leaves_out_fixture_setup(project, monkeypatch):
    """--phases run credits a test with what its body ran, not its fixtures."""
    result = run_pytest(project, "--recov-context=test")
    assert result.returncode == 0, result.stdout + result.stderr

    every_phase = lines_by_context(monkeypatch, project)
    run_only = lines_by_context(monkeypatch, project, phases={"run"})

    # test_d only reaches only_in_a() through its fixture...
    assert ONLY_LINE in every_phase["tests/test_d.py::test_d"]
    # ...so with --phases run it is credited with nothing at all, and stays
    # visible rather than dropping out of the report.
    assert run_only["tests/test_d.py::test_d"] == set()

    # A test body that really does run the line keeps it.
    assert run_only["tests/test_a.py::test_a"] == {SHARED_LINE, ONLY_LINE}


def test_flat_pytest_cov_contexts_still_work(project, monkeypatch):
    """Without --recov-context the plugin stays out of the way."""
    result = run_pytest(project, "--cov-context=test", env_extra={"COVERAGE_CORE": "ctrace"})
    assert result.returncode == 0, result.stdout + result.stderr

    covered = lines_by_context(monkeypatch, project)
    assert "tests/test_a.py::test_a" in covered


@sysmon_only
def test_sysmon_core_is_rejected(project):
    """The core that silently drops contexts fails the run instead."""
    result = run_pytest(project, "--recov-context=test", env_extra={"COVERAGE_CORE": "sysmon"})
    assert result.returncode != 0
    assert "sysmon" in result.stdout + result.stderr


@sysmon_only
def test_sysmon_core_loses_tests(project, monkeypatch):
    """Document the behaviour this plugin exists to prevent."""
    result = run_pytest(
        project,
        "--recov-context=test",
        "--recov-no-core-fixup",
        env_extra={"COVERAGE_CORE": "sysmon"},
    )
    assert result.returncode == 0, result.stdout + result.stderr

    covered = lines_by_context(monkeypatch, project)
    runners = {ctx for ctx, lines in covered.items() if SHARED_LINE in lines}
    if len(runners) == 3:
        pytest.skip("coverage's sysmon core now honours contexts; the core fixup is obsolete")
    assert len(runners) == 1
