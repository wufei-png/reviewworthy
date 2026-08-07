# Contributing to Reviewworthy

Reviewworthy is maintained with its own maintainer-first workflow. A normal contribution must begin with a public GitHub Issue; the verified Issue may be pending, and a maintainer reply is not required before implementation. Security reports are the exception and must follow `SECURITY.md`.

AI assistance is allowed. AI assistance must be disclosed in the PR body, and the PR description must be written in the contributor's own words before it is submitted. Draft pull requests are required until the exact narrative and verification evidence are ready. Good-first-issue work with AI assistance is permitted when the Issue and repository policy allow it.

Before implementation, contributors should inspect policy, create a Project Brief, record duplicate-work evidence with an explicit disposition, bind the selected basis to a Contribution Packet, and approve a Contribution Contract. Capture the real Git diff and verification receipt with the CLI. Standard Understanding must cover behavior, invariant, and test; heightened work also covers flow, trade-offs, failures, and regressions.

For a local checkout, the regression commands are:

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m reviewworthy eval run --json
PYTHONPATH=src python -m reviewworthy action check --mode report --changed-files-unavailable
```

Future repository changes should be prepared and submitted through a Reviewworthy PR. The final PR Body must include the supporting Issue URL, and the one-line PR URL note is written back to that Issue only after the PR is created. The remote operation ID shown by `remote plan` must be explicitly confirmed; branch protection and required checks remain maintainer-controlled repository settings.
