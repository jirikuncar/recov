"""Unit tests for nested coverage contexts."""

import pytest

from recov import analysis_context
from recov.contexts import (
    FRAME_SEPARATOR,
    CoverageContextStack,
    LossyCoreError,
    active_core_name,
    decode_context,
    display_context,
    encode_context,
    ensure_context_capable_core,
    iter_ancestors,
    truncate_context,
    verify_context_capable_core,
)

US = FRAME_SEPARATOR


def test_encode_round_trips():
    name = encode_context(["test_a", "step"], "run")
    assert name == f"test_a{US}step|run"
    assert decode_context(name) == (("test_a", "step"), "run")


def test_encode_without_phase():
    assert encode_context(["test_a"]) == "test_a"
    assert decode_context("test_a") == (("test_a",), None)


def test_decode_flat_pytest_cov_context():
    """Data collected by plain pytest-cov still decodes to a single frame."""
    nodeid = "tests/test_x.py::TestThing::test_y[a|b]"
    assert decode_context(f"{nodeid}|setup") == ((nodeid,), "setup")
    assert decode_context(nodeid) == ((nodeid,), None)


def test_decode_keeps_node_id_intact():
    frames, phase = decode_context("tests/test_x.py::test_y|teardown")
    assert frames == ("tests/test_x.py::test_y",)
    assert phase == "teardown"


def test_decode_empty():
    assert decode_context("") == ((), None)


@pytest.mark.parametrize(
    ("depth", "expected"),
    [
        (1, "a"),
        (2, f"a{US}b"),
        (3, f"a{US}b{US}c"),
        (9, f"a{US}b{US}c"),
        (0, f"a{US}b{US}c"),
        (-1, f"a{US}b{US}c"),
    ],
)
def test_truncate_context(depth, expected):
    assert truncate_context(f"a{US}b{US}c|run", depth) == expected


def test_truncate_drops_phase():
    assert truncate_context("test_a|setup", 1) == "test_a"
    assert truncate_context("test_a|teardown", 0) == "test_a"


def test_iter_ancestors():
    assert list(iter_ancestors(f"a{US}b{US}c|run")) == ["a", f"a{US}b", f"a{US}b{US}c"]
    assert list(iter_ancestors("")) == []


def test_display_context():
    assert display_context(f"a{US}b|run") == "a ▸ b|run"
    assert display_context("a") == "a"


def test_analysis_context_maps_empty_to_global():
    assert analysis_context("", 1) == "global"
    assert analysis_context(None, 1) == "global"
    assert analysis_context("|run", 1) == "global"


def test_analysis_context_rolls_nested_up_to_the_test():
    assert analysis_context(f"tests/t.py::test_a{US}step|run", 1) == "tests/t.py::test_a"
    assert analysis_context("tests/t.py::test_a|setup", 1) == "tests/t.py::test_a"


class FakeCoverage:
    """Just enough of coverage.Coverage to observe context switches."""

    def __init__(self, started=True):
        self._started = started
        self.switches: list[str] = []

    def switch_context(self, name):
        self.switches.append(name)


def test_stack_pushes_whole_stack_into_coverage():
    cov = FakeCoverage()
    stack = CoverageContextStack(cov)

    stack.push("test_a")
    stack.set_phase("run")
    stack.push("step")
    assert stack.frames == ("test_a", "step")
    assert stack.current() == f"test_a{US}step|run"
    assert stack.pop() == "step"
    stack.reset()

    assert cov.switches == [
        "test_a",
        "test_a|run",
        f"test_a{US}step|run",
        "test_a|run",
        "",
    ]


def test_stack_context_manager_pops_on_error():
    cov = FakeCoverage()
    stack = CoverageContextStack(cov)
    stack.push("test_a")

    with pytest.raises(ValueError), stack.context("step"):
        raise ValueError("boom")

    assert stack.frames == ("test_a",)


def test_stack_is_a_noop_when_coverage_is_not_started():
    cov = FakeCoverage(started=False)
    stack = CoverageContextStack(cov)
    stack.push("test_a")
    assert stack.frames == ("test_a",)
    assert cov.switches == []


def test_stack_rejects_separator_in_label():
    stack = CoverageContextStack(FakeCoverage())
    with pytest.raises(ValueError):
        stack.push(f"a{US}b")
    with pytest.raises(ValueError):
        stack.push("a|b")


def test_set_phase_rejects_unknown_phases():
    stack = CoverageContextStack(FakeCoverage())
    with pytest.raises(ValueError, match="phase"):
        stack.set_phase("whenever")


def test_stack_pop_on_empty_stack():
    stack = CoverageContextStack(FakeCoverage())
    with pytest.raises(IndexError):
        stack.pop()


def test_ensure_context_capable_core_respects_explicit_choice():
    env = {"COVERAGE_CORE": "sysmon"}
    assert ensure_context_capable_core(env) is None
    assert env == {"COVERAGE_CORE": "sysmon"}


def test_ensure_context_capable_core_sets_a_core_when_sysmon_is_the_default(monkeypatch):
    from coverage import env as coverage_env

    monkeypatch.setattr(coverage_env, "SYSMON_DEFAULT", True, raising=False)
    environ: dict[str, str] = {}
    chosen = ensure_context_capable_core(environ)
    assert chosen in {"ctrace", "pytrace"}
    assert environ == {"COVERAGE_CORE": chosen}


def test_ensure_context_capable_core_leaves_older_pythons_alone(monkeypatch):
    from coverage import env as coverage_env

    monkeypatch.setattr(coverage_env, "SYSMON_DEFAULT", False, raising=False)
    environ = {}
    assert ensure_context_capable_core(environ) is None
    assert environ == {}


class FakeCore:
    def __init__(self, name):
        self.tracer_class = type(name, (), {})


class FakeCollector:
    def __init__(self, name):
        self.core = FakeCore(name)


class FakeStartedCoverage:
    def __init__(self, name):
        self._collector = FakeCollector(name)


def test_active_core_name():
    assert active_core_name(FakeStartedCoverage("SysMonitor")) == "sysmon"
    assert active_core_name(FakeStartedCoverage("CTracer")) == "ctrace"
    assert active_core_name(FakeStartedCoverage("PyTracer")) == "pytrace"
    assert active_core_name(object()) is None


def test_verify_context_capable_core_rejects_sysmon():
    with pytest.raises(LossyCoreError, match="sysmon"):
        verify_context_capable_core(FakeStartedCoverage("SysMonitor"))


def test_verify_context_capable_core_accepts_tracing_cores():
    verify_context_capable_core(FakeStartedCoverage("CTracer"))
    verify_context_capable_core(FakeStartedCoverage("PyTracer"))
    verify_context_capable_core(object())
