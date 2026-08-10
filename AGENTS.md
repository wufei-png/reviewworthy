# Repository Guidelines

## Project Structure & Module Organization

Reviewworthy is a Python 3.11+ CLI with no third-party runtime dependencies. Package code lives in `src/reviewworthy/`; `cli.py` defines command routing, while modules such as `packet.py`, `policy.py`, and `action.py` own deterministic domain behavior. Tests are in `tests/` and generally mirror package modules (`tests/test_packet.py`). JSON contracts live in `schemas/`, fixture evaluations in `evals/fixtures/`, reusable documents in `templates/`, and architecture decisions in `docs/adr/`. The composite GitHub Action is defined by `action.yml`.

## Build, Test, and Development Commands

- `python -m pip install -r requirements-dev.txt` installs the test-only schema validator.
- `PYTHONPATH=src python -m unittest discover -s tests -v` runs the full regression suite.
- `PYTHONPATH=src python -m reviewworthy eval run --json` checks policy and workflow evaluation fixtures.
- `PYTHONPATH=src python -m reviewworthy action check --mode report` exercises the read-only Action path.
- `python -m pip install -e .` installs the local `reviewworthy` console command.
- `python -m pip wheel --no-deps --no-build-isolation .` verifies package construction; install `setuptools>=68` first.

## Coding Style & Naming Conventions

Use four-space indentation, standard-library imports before local imports, type hints for public and nontrivial internal APIs, and concise module docstrings. Name modules, functions, and variables with `snake_case`; use `PascalCase` for classes and `UPPER_CASE` for constants. Keep provider access, persistence, and remote writes explicit; preserve the deterministic CLI boundary described in `docs/adr/`. The repository has no configured autoformatter or linter, so match nearby code and run `python -m compileall -q src tests` before submission.

## Testing Guidelines

Tests use `unittest`; classes end in `Tests` and methods begin with `test_`. Add focused regression tests beside the affected module and update schema or eval fixtures when contracts change. There is no numeric coverage threshold, but CI runs the full suite on Python 3.11, 3.12, and 3.13 and separately validates schemas and generated artifacts.

## Commit & Pull Request Guidelines

Follow the recent Conventional Commit style: `feat: ...`, `fix: ...`, `docs: ...`, or `ci: ...`. Keep each commit cohesive and imperative. External contributions must start from a public GitHub Issue (security reports use the private advisory flow), remain draft until ready, disclose AI assistance, link the supporting Issue, and include verification evidence in the contributor's own PR narrative. Follow `CONTRIBUTING.md` and never publish secrets or vulnerability details.
