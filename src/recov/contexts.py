"""Nested coverage contexts.

Coverage.py records every measured line against exactly one context: the one
that is current when the line runs.  That is a problem when you want to know
*which tests* execute a given line, for two reasons:

1. On CPython 3.14+ coverage defaults to the ``sysmon`` core, which is built on
   :mod:`sys.monitoring`.  That core permanently disables the line event for a
   code location once it has been seen (``sys.monitoring.DISABLE``) and it
   ignores context switches altogether.  In a single process only the *first*
   test that runs a line is recorded; every later test that runs the same line
   is silently dropped.  Spawning one process per test hides the problem, at
   the cost of a very slow test run.  :func:`ensure_context_capable_core` and
   :func:`verify_context_capable_core` keep that from happening.

2. Contexts do not nest.  ``switch_context()`` replaces the current label, so a
   sub-context started inside a test hides the test itself for as long as it is
   active.

This module solves (2) by keeping an explicit *stack* of labels and encoding the
whole stack into the context name that coverage records, so nothing is hidden:

    ``tests/test_api.py::test_get<US>request<US>retry|run``

``<US>`` is :data:`FRAME_SEPARATOR` (ASCII unit separator), which cannot appear
in a pytest node id, and ``|run`` is the phase separator that ``pytest-cov``
already uses.  Reading the data back (see :func:`truncate_context`) rolls a
nested context up into any of its ancestors, so a line executed three levels
deep still counts for the test that ran it.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from typing import Final

from coverage import Coverage, CoverageException
from coverage import env as coverage_env

__all__ = [
    "CORE_BY_TRACER",
    "DISPLAY_SEPARATOR",
    "FRAME_SEPARATOR",
    "PHASES",
    "PHASE_SEPARATOR",
    "LOSSY_CORES",
    "CoverageContextStack",
    "LossyCoreError",
    "active_core_name",
    "context",
    "decode_context",
    "display_context",
    "encode_context",
    "ensure_context_capable_core",
    "iter_ancestors",
    "stack",
    "truncate_context",
    "verify_context_capable_core",
]

#: Separates the frames of a nested context inside a recorded context name.
#: ASCII "unit separator": it cannot occur in a pytest node id or a file path.
FRAME_SEPARATOR: Final = "\x1f"

#: Separates the context name from the phase, as used by ``pytest-cov``
#: (``"tests/test_x.py::test_y|setup"``).
PHASE_SEPARATOR: Final = "|"

#: What :func:`display_context` puts between frames when showing a context.
DISPLAY_SEPARATOR: Final = " ▸ "

#: Phase suffixes recorded after :data:`PHASE_SEPARATOR`. These are the ones
#: ``pytest-cov`` uses, and the only ones treated as a phase when decoding --
#: anything else stays part of the context, so a parametrised node id such as
#: ``test_x[a|b]`` survives a round trip.
PHASES: Final = frozenset({"setup", "run", "teardown"})

#: Maps coverage's tracer classes back onto the core names users configure.
CORE_BY_TRACER: Final = {
    "SysMonitor": "sysmon",
    "CTracer": "ctrace",
    "PyTracer": "pytrace",
}

#: Coverage cores that silently drop data when contexts are switched.
LOSSY_CORES: Final = frozenset({"sysmon"})


# --------------------------------------------------------------------------
# Encoding / decoding
# --------------------------------------------------------------------------


def encode_context(frames: Sequence[str], phase: str | None = None) -> str:
    """Encode a context stack (and optional phase) into a coverage context name.

    >>> encode_context(["test_a", "step"], "run") == "test_a\\x1fstep|run"
    True
    """
    name = FRAME_SEPARATOR.join(frames)
    if phase:
        name = f"{name}{PHASE_SEPARATOR}{phase}"
    return name


def decode_context(context: str) -> tuple[tuple[str, ...], str | None]:
    """Split a recorded context name into its frames and its phase.

    A context recorded by plain ``pytest-cov`` has a single frame, so this is
    backwards compatible with coverage data collected without ``recov``.

    Only a trailing :data:`PHASES` value counts as a phase, so a parametrised
    node id that happens to contain a pipe is left alone.

    >>> decode_context("tests/test_x.py::test_y|run")
    (('tests/test_x.py::test_y',), 'run')
    >>> decode_context("tests/test_x.py::test_y[a|b]")
    (('tests/test_x.py::test_y[a|b]',), None)
    """
    stem, sep, tail = context.rpartition(PHASE_SEPARATOR)
    if sep and tail in PHASES:
        phase: str | None = tail
    else:
        stem, phase = context, None
    frames = tuple(frame for frame in stem.split(FRAME_SEPARATOR) if frame)
    return frames, phase


def truncate_context(context: str, depth: int) -> str:
    """Roll a recorded context up to at most `depth` frames.

    This is what makes nested contexts usable for analysis: coverage collected
    under ``test ▸ request ▸ retry`` is attributed to ``test`` at depth 1, to
    ``test ▸ request`` at depth 2, and so on.  The phase is always dropped, so
    ``setup``, ``run`` and ``teardown`` of one test merge together.

    `depth` of 0 (or less) keeps the full stack.
    """
    frames, _phase = decode_context(context)
    if depth > 0:
        frames = frames[:depth]
    return FRAME_SEPARATOR.join(frames)


def iter_ancestors(context: str) -> Iterator[str]:
    """Yield every context that `context` contributes to, outermost first.

    ``"a<US>b<US>c|run"`` yields ``"a"``, ``"a<US>b"``, ``"a<US>b<US>c"``.
    """
    frames, _phase = decode_context(context)
    for i in range(1, len(frames) + 1):
        yield FRAME_SEPARATOR.join(frames[:i])


def display_context(context: str) -> str:
    """Render a recorded or truncated context name for humans."""
    frames, phase = decode_context(context)
    shown = DISPLAY_SEPARATOR.join(frames)
    return f"{shown}{PHASE_SEPARATOR}{phase}" if phase else shown


# --------------------------------------------------------------------------
# Core selection
# --------------------------------------------------------------------------


def active_core_name(cov: object) -> str | None:
    """Return the name of the core a started :class:`coverage.Coverage` uses.

    Returns ``None`` when the core cannot be determined (coverage is not
    started, or coverage changed its internals).
    """
    collector = getattr(cov, "_collector", None)
    core = getattr(collector, "core", None)
    tracer_class = getattr(core, "tracer_class", None)
    if tracer_class is None:
        return None
    tracer_name = str(tracer_class.__name__)
    return CORE_BY_TRACER.get(tracer_name, tracer_name)


def _preferred_core() -> str:
    """The best context-capable core available in this interpreter."""
    try:
        import coverage.tracer  # noqa: F401
    except ImportError:
        return "pytrace"
    return "ctrace"


def ensure_context_capable_core(environ: dict[str, str] | None = None) -> str | None:
    """Point coverage at a core that records contexts, before it starts.

    Coverage reads ``COVERAGE_CORE`` when it starts and lets it win over the
    config file, so setting it here is enough — but it only works *before*
    :meth:`coverage.Coverage.start`.  An explicit ``COVERAGE_CORE`` is left
    alone: choosing the core is the user's call, and
    :func:`verify_context_capable_core` reports the consequences later.

    Returns the core that was selected, or ``None`` if nothing was changed.
    """
    env = os.environ if environ is None else environ
    if env.get("COVERAGE_CORE"):
        return None

    # sysmon is only ever picked by default; on older Pythons the default core
    # already records contexts and there is nothing to fix.
    if not getattr(coverage_env, "SYSMON_DEFAULT", False):
        return None

    core = _preferred_core()
    env["COVERAGE_CORE"] = core
    return core


class LossyCoreError(RuntimeError):
    """Raised when the running coverage core cannot record contexts."""


def verify_context_capable_core(cov: object) -> None:
    """Fail loudly if the started coverage `cov` will drop context data."""
    core = active_core_name(cov)
    if core not in LOSSY_CORES:
        return
    raise LossyCoreError(
        f"coverage is running with the {core!r} core, which ignores coverage "
        "contexts and records each line only once per process. Per-test "
        "coverage would be wrong. Set COVERAGE_CORE=ctrace in the environment "
        "(or 'core = \"ctrace\"' under [tool.coverage.run]) before starting "
        "coverage."
    )


# --------------------------------------------------------------------------
# The context stack
# --------------------------------------------------------------------------


class CoverageContextStack:
    """A stack of labels mirrored into coverage's current context.

    Pushing a label appends a frame; the context coverage records is the whole
    stack joined with :data:`FRAME_SEPARATOR`.  Coverage's context is global to
    the process, so this stack is too — it is guarded by a lock but it does not
    give each thread its own stack, because coverage could not honour that.
    """

    def __init__(self, coverage: object | None = None) -> None:
        self._coverage = coverage
        self._frames: list[str] = []
        self._phase: str | None = None
        self._lock = threading.RLock()

    # -- state ------------------------------------------------------------

    @property
    def frames(self) -> tuple[str, ...]:
        """The labels currently on the stack, outermost first."""
        return tuple(self._frames)

    @property
    def phase(self) -> str | None:
        """The current phase, recorded after :data:`PHASE_SEPARATOR`."""
        return self._phase

    def current(self) -> str:
        """The context name coverage is currently recording under."""
        return encode_context(self._frames, self._phase)

    # -- mutation ---------------------------------------------------------

    def push(self, label: str) -> None:
        """Enter a nested context called `label`."""
        if FRAME_SEPARATOR in label or PHASE_SEPARATOR in label:
            raise ValueError(f"context label may not contain separators: {label!r}")
        with self._lock:
            self._frames.append(label)
            self._sync()

    def pop(self) -> str:
        """Leave the innermost context and return its label."""
        with self._lock:
            if not self._frames:
                raise IndexError("coverage context stack is empty")
            label = self._frames.pop()
            self._sync()
            return label

    def set_phase(self, phase: str | None) -> None:
        """Set the phase suffix, one of :data:`PHASES`, or ``None`` to clear it.

        Phases are deliberately a closed set: an arbitrary suffix could not be
        told apart from a node id containing a pipe when the data is read back.
        Use :meth:`push` for finer granularity.
        """
        if phase is not None and phase not in PHASES:
            raise ValueError(f"unknown coverage context phase: {phase!r}")
        with self._lock:
            self._phase = phase
            self._sync()

    def reset(self) -> None:
        """Drop every frame and return coverage to the global context."""
        with self._lock:
            self._frames.clear()
            self._phase = None
            self._sync()

    @contextmanager
    def context(self, label: str) -> Iterator[None]:
        """Record everything executed in this block under a nested `label`."""
        self.push(label)
        try:
            yield
        finally:
            self.pop()

    # -- plumbing ---------------------------------------------------------

    def _resolve_coverage(self) -> object | None:
        if self._coverage is not None:
            return self._coverage
        return Coverage.current()

    def _sync(self) -> None:
        """Push the current stack into coverage, if coverage is running."""
        cov = self._resolve_coverage()
        if cov is None or getattr(cov, "_started", True) is False:
            return
        switch_context = getattr(cov, "switch_context", None)
        if switch_context is None:  # pragma: no cover - defensive
            return
        # Coverage may stop between resolving it and switching contexts.
        with suppress(CoverageException):
            switch_context(self.current())


#: The process-wide stack used by the pytest plugin and by :func:`context`.
stack = CoverageContextStack()


@contextmanager
def context(label: str) -> Iterator[None]:
    """Record everything executed in this block under a nested `label`.

    Usable anywhere while coverage is running; a no-op when it is not::

        with recov.context("second request"):
            client.get("/")
    """
    with stack.context(label):
        yield
