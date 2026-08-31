# recov: Optimize Test Suites & Speed Up CI/CD

## Motivation

Modern software projects often accumulate large test suites, but not all tests contribute unique value. Redundant tests slow down CI/CD pipelines, waste compute resources, and obscure true coverage gaps. `recov` helps you identify and remove tests that do not contribute unique coverage, so you can:

- **Speed up CI/CD** by running only the essential tests
- **Reduce maintenance** by focusing on meaningful tests

## Features
- Detects redundant tests using coverage data (lines and branches)
- Records **every** test that executes a line, in a single pytest process — no spawning one process per test
- Supports **nested** coverage contexts, so a context started inside a test does not hide the test
- Rich terminal output for easy review
- Works with pytest-cov and Coverage.py
- CLI and Python API

## Quickstart

1. Run your tests with `recov`'s coverage contexts:
   ```bash
   pytest --cov=src --cov-branch --recov-context=test
   ```
2. Analyze for redundant tests:
   ```bash
   uvx recov  # or use the CLI entrypoint
   ```

`--recov-context=test` comes from the pytest plugin that ships with `recov`; it
is registered automatically once `recov` is installed. It replaces
pytest-cov's `--cov-context=test` — see below for why you want it.

## Why not just `--cov-context=test`?

Per-test coverage collected in one process loses data, in two ways.

### 1. Coverage's `sysmon` core records each line only once per process

On CPython 3.14+ coverage defaults to the `sysmon` core, built on
[`sys.monitoring`](https://docs.python.org/3/library/sys.monitoring.html). For
speed, that core returns `sys.monitoring.DISABLE` after a line's first hit,
permanently switching the line's events off, and it ignores context switches
altogether. The result: whichever test happens to run a line *first* is
credited with it, and every later test that runs the same line is silently
dropped. Three tests calling the same function:

```
''                            [1, 4, 9, 10, 14]
'tests/test_a.py::test_a|run' [5, 6, 11, 15]     ← test_b and test_c vanish
```

That is what pushes people into spawning one process per test. `recov`'s plugin
instead selects a context-capable core (`COVERAGE_CORE=ctrace`) *before*
coverage starts, and fails the run loudly rather than quietly producing wrong
data if it cannot:

```
''                            [1, 4, 9, 10, 14]
'tests/test_a.py::test_a|run' [5, 6, 11, 15]
'tests/test_b.py::test_b|run' [5, 6]
'tests/test_c.py::test_c|run' [5, 6, 15]
```

If you already have a `.coverage` file collected this way, `recov` points out
the signature — no line covered by more than one test — and tells you how to
re-collect.

### 2. Coverage contexts do not nest

`Coverage.switch_context()` *replaces* the current label, so any context
started inside a test hides the test for as long as it is active. `recov`
keeps an explicit stack of labels and encodes the whole stack into the
recorded context name, separated by the ASCII unit separator (`\x1f`, shown as
`▸` in output) — which cannot occur in a pytest node id:

```
tests/test_api.py::test_retry ▸ first attempt|run
tests/test_api.py::test_retry ▸ retry|run
```

Reading the data back rolls a nested context up into each of its ancestors, so
a line executed three levels deep still counts for the test that ran it.

## Nesting contexts in your tests

Use the `recov_context` fixture:

```python
def test_retries(client, recov_context):
    with recov_context("first attempt"):
        client.get("/")
    with recov_context("retry"):
        client.get("/")
```

the `recov_context` marker, to wrap a whole test:

```python
@pytest.mark.recov_context("integration")
def test_end_to_end(): ...
```

or `recov.context()` anywhere in your own code (a no-op when coverage is not
running):

```python
import recov

with recov.context("cache warm"):
    warm_the_cache()
```

## Reporting only what test bodies ran

Coverage collected during a test's fixtures is recorded under `…|setup` and
`…|teardown`, and the test body's under `…|run`. By default all three count
towards the test. `--phases run` credits a test with only what its own body
executed:

```bash
recov --phases run
```

A test that only reaches a line through a fixture then shows up with nothing
of its own:

```
┃ Test                    ┃ Covered Items ┃ Lines Overlap % ┃ Status    ┃
│ tests/test_a.py::test_a │             5 │            0.0% │ UNIQUE    │
│ tests/test_b.py::test_b │             0 │             N/A │ REDUNDANT │
```

Tests whose every row was filtered out stay in the report rather than
disappearing — a test body that covers nothing new is the result you were
looking for.

Coverage that belongs to no selected test — imports, and the phases you
excluded — becomes the **baseline**. It still counts as covered, so:

- nothing is reported as a coverage gap just because a fixture covered it, and
- a test is not called unique for a line its own fixture covered.

The summary reports it separately:

```
• Total lines covered: 2
• Lines covered outside the analyzed tests: 6 (imports and excluded phases)
```

Pass `--no-baseline` to ignore that coverage entirely instead.

## Usage

- By default, `recov` analyzes line coverage. Use `--with-branches` to require branch coverage.
- `--phases run` (or any comma-separated subset of `setup,run,teardown`,
  default: all) chooses which pytest phases count towards a test. Contexts
  carrying no phase at all are always kept.
- `--no-baseline` stops coverage recorded outside the analyzed tests from
  counting as already covered.
- `--context-depth N` chooses the granularity of the analysis when nested
  contexts were recorded. `1` (the default) compares whole tests, `2` compares
  the sub-contexts nested directly inside each test, and `0` compares the
  innermost contexts recorded. Only contexts at one depth are compared, so a
  test is never reported as redundant against its own sub-contexts.
- Results show which tests are redundant (their coverage is fully covered by other tests).
- Remove or refactor redundant tests to optimize your suite and speed up CI/CD.

### Collecting without the pytest plugin

If you drive coverage yourself, set the core before coverage starts and drive
`recov.stack` directly:

```toml
# pyproject.toml
[tool.coverage.run]
core = "ctrace"
```

```python
import recov

with recov.context("test_a"):
    ...
```

## Known limits

- Lines that only run at **import time** are recorded against the global
  context, because they execute during collection, before any test starts. No
  test is credited with them — they are counted as baseline coverage instead,
  so they never show up as a gap.
- Results memoized by the code under test (`functools.lru_cache`, module-level
  singletons) are computed once, so only the test that ran first is credited —
  that is a true record of what executed, not a coverage defect.
- The context stack is process-global, because coverage's current context is.
  Tests running concurrently in threads within one process cannot be attributed
  separately. `pytest-xdist` is fine: each worker is its own process.

## Development & Contributing

Contributions welcome: open issues or PRs to improve detection, performance, or usability.

## AI Use Disclaimer

This tool has been built with a lot of support of AI.

## License

MIT
