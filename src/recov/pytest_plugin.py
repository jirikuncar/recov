"""A pytest plugin that records complete, nested per-test coverage contexts.

Two things go wrong when per-test coverage is collected in a single process,
and this plugin fixes both:

* On CPython 3.14+ coverage defaults to the ``sysmon`` core, which ignores
  context switches and records each line only once per process, so only the
  first test that runs a line is credited with it.  The plugin selects a
  context-capable core before coverage starts, and refuses to run quietly if
  it cannot.
* ``pytest-cov`` sets one flat context per test, so a context started inside a
  test hides the test itself.  The plugin drives
  :data:`recov.contexts.stack` instead, which encodes the whole stack into the
  recorded context name so nothing is hidden.

Enable it with ``--recov-context=test`` (in place of ``--cov-context=test``)::

    pytest --cov=src --cov-branch --recov-context=test

Inside a test, nest further contexts with the ``recov_context`` fixture, the
``recov_context`` marker, or :func:`recov.context`.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

import pytest

from recov.contexts import (
    CoverageContextStack,
    LossyCoreError,
    ensure_context_capable_core,
    stack,
    verify_context_capable_core,
)

if TYPE_CHECKING:
    from _pytest.config import Config
    from _pytest.config.argparsing import Parser

#: The name ``pytest-cov`` registers its own (flat) context plugin under.
PYTEST_COV_CONTEXT_PLUGIN = "_cov_contexts"


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("recov")
    group.addoption(
        "--recov-context",
        action="store",
        default=None,
        choices=["test"],
        help=(
            "Record nested coverage contexts per test, so that every test "
            "executing a line is recorded in a single process. Use instead of "
            "--cov-context=test."
        ),
    )
    group.addoption(
        "--recov-no-core-fixup",
        action="store_true",
        default=False,
        help=(
            "Do not select a context-capable coverage core, and do not fail "
            "when the running core drops contexts. Only useful for "
            "reproducing the data loss this plugin exists to prevent."
        ),
    )


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config: Config) -> None:
    """Select a context-capable core before ``pytest-cov`` starts coverage.

    Coverage reads ``COVERAGE_CORE`` in :meth:`coverage.Coverage.start`, and
    ``pytest-cov`` starts coverage from this same hook, so this is the last
    moment at which the core can still be chosen.
    """
    known = early_config.known_args_namespace
    if getattr(known, "recov_context", None) is None:
        return
    if getattr(known, "recov_no_core_fixup", False):
        return
    ensure_context_capable_core()


def pytest_configure(config: Config) -> None:
    config.addinivalue_line(
        "markers",
        "recov_context(label): record this test's coverage under a nested context label.",
    )
    if config.getoption("recov_context") is None:
        return
    config.pluginmanager.register(RecovContextPlugin(config), "recov_contexts")


class RecovContextPlugin:
    """Drives the nested coverage context stack across a test run."""

    def __init__(self, config: Config, context_stack: CoverageContextStack | None = None) -> None:
        self.config = config
        self.stack = stack if context_stack is None else context_stack

    # -- session ----------------------------------------------------------

    @pytest.hookimpl(trylast=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        # pytest-cov registers its flat context plugin from pytest_sessionstart
        # too; running trylast lets us take over from it rather than fight it.
        manager = session.config.pluginmanager
        flat = manager.get_plugin(PYTEST_COV_CONTEXT_PLUGIN)
        if flat is not None:
            manager.unregister(flat, PYTEST_COV_CONTEXT_PLUGIN)
        self._verify_core()

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        self.stack.reset()

    def _verify_core(self) -> None:
        """Fail the run if the started coverage would drop contexts."""
        if self.config.getoption("recov_no_core_fixup"):
            return
        from coverage import Coverage

        cov = Coverage.current()
        if cov is None:
            return
        try:
            verify_context_capable_core(cov)
        except LossyCoreError as exc:
            raise pytest.UsageError(str(exc)) from exc

    # -- per test ---------------------------------------------------------

    def _labels(self, item: pytest.Item) -> list[str]:
        """The context frames to push for `item`, outermost first."""
        labels = [item.nodeid]
        for marker in item.iter_markers(name="recov_context"):
            labels.extend(str(arg) for arg in marker.args)
        return labels

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item) -> Generator[None, object, object]:
        labels = self._labels(item)
        for label in labels:
            self.stack.push(label)
        try:
            return (yield)
        finally:
            for _ in labels:
                self.stack.pop()
            self.stack.set_phase(None)

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        self.stack.set_phase("setup")

    def pytest_runtest_call(self, item: pytest.Item) -> None:
        self.stack.set_phase("run")

    def pytest_runtest_teardown(self, item: pytest.Item) -> None:
        self.stack.set_phase("teardown")


@pytest.fixture
def recov_context() -> Callable[[str], AbstractContextManager[None]]:
    """Nest a coverage context inside the current test.

    ::

        def test_retries(client, recov_context):
            with recov_context("first attempt"):
                client.get("/")
            with recov_context("retry"):
                client.get("/")

    Coverage collected inside the block is recorded under the nested context
    *and* still counts for the test, because :mod:`recov` rolls a nested
    context up into its ancestors when it reads the data back.
    """
    return stack.context
