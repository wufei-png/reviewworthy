# Contributing to Reviewworthy

Reviewworthy applies its maintainer-first contribution workflow to external contributors. An external contribution must begin with a public GitHub Issue; the verified Issue may be pending, and a maintainer reply is not required before implementation. Security reports are the exception and must follow `SECURITY.md`.

AI assistance is allowed. AI assistance must be disclosed in the PR body, and the PR description must be written in the contributor's own words before it is submitted. Draft pull requests are required until the exact narrative and verification evidence are ready. Good-first-issue work with AI assistance is permitted when the Issue and repository policy allow it.

Before implementation, contributors should inspect policy, create a Project Brief, record duplicate-work evidence with an explicit disposition, bind the selected basis to a Contribution Packet, and approve a Contribution Contract. Capture the real Git diff and verification receipt with the CLI. Standard requires the light Ownership Check; Heightened and Learning additionally require full Orientation and Assessment across behavior, invariants, tests, flow, trade-offs, failures, and regressions.

For a local checkout, the regression commands are:

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m reviewworthy eval run --json
PYTHONPATH=src python -m reviewworthy action check --mode report --changed-files-unavailable
```

External contributions must be prepared and submitted through a Reviewworthy PR. The final PR Body must include the supporting Issue URL, and the one-line PR URL note is written back to that Issue only after the PR is created. The remote operation ID shown by `remote plan` must be explicitly confirmed.

A maintainer-authorized repository change may be pushed directly under the project's own governance. Direct push does not waive tests, review judgment, CI, release evidence, or security handling; it only means Reviewworthy does not force maintainers to dogfood the external-contribution PR protocol. Repository workflows own event and actor routing, while branch protection and required checks remain maintainer-controlled settings.
