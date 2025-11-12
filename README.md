# recov: Optimize Test Suites & Speed Up CI/CD

## Motivation

Modern software projects often accumulate large test suites, but not all tests contribute unique value. Redundant tests slow down CI/CD pipelines, waste compute resources, and obscure true coverage gaps. `recov` helps you identify and remove tests that do not contribute unique coverage, so you can:

- **Speed up CI/CD** by running only the essential tests
- **Reduce maintenance** by focusing on meaningful tests

## Features
- Detects redundant tests using coverage data (lines and branches)
- Fast, in-memory analysis with DuckDB and PyArrow
- Rich terminal output for easy review
- Works with pytest-cov and Coverage.py
- CLI and Python API

## Quickstart

1. Run your tests with coverage contexts:
   ```bash
   pytest --cov=src --cov-context=test --cov-branch --cov-append
   ```
2. Analyze for redundant tests:
   ```bash
   uvx recov  # or use the CLI entrypoint
   ```

## Usage

- By default, `recov` analyzes line coverage. Use `--with-branches` to require branch coverage.
- Results show which tests are redundant (their coverage is fully covered by other tests).
- Remove or refactor redundant tests to optimize your suite and speed up CI/CD.


## Development & Contributing

Contributions welcome: open issues or PRs to improve detection, performance, or usability.

## AI Use Disclaimer

This tool has been built with a lot of support of AI.

## License

MIT
