# Action, eval, and Schema CI

The composite Action is intentionally read-only. Its default `report` mode preserves the conservative behavior used by existing consumers: a missing Packet or unknown policy/evidence is reported and does not fail the check. A repository that explicitly chooses enforcement can set `mode: enforce`, or turn on `require-packet`, `require-current-diff`, and `fail-on-unknown` individually.

`enforce` means:

- a Contribution Packet must exist and be valid;
- the event must be a real `pull_request` with base/head SHAs and those local commit objects must already exist;
- the Packet repository must match the runner event's case-insensitive `owner/name` slug and exact numeric repository ID;
- the Action recomputes the merge-base contribution Diff through the shared `capture_pr_diff()` implementation and compares comparison mode, base tip SHA, merge base SHA, head SHA, patch hash, changed files, additions, and deletions with the Packet;
- a successful CLI verification receipt must have `exit_code=0`, a valid status, clean worktree before/after, stable `head_sha_before == head_sha == head_sha_after`, and a head bound to the current PR;
- unknown policy or deterministic evidence becomes a violation.

The Action does not fetch missing objects. A hand-supplied `changed-files` input is allowed only as report-mode evidence and is ignored by enforce mode; it cannot replace the complete current Diff. Report mode may describe missing PR objects, repository identity, or receipt evidence as unknown. The repository's workflow uses `actions/checkout` with `fetch-depth: 0` so the required commit objects are available.

The Action still does not infer maintainer approval, call `gh`, create Issues/PRs, or decide whether a human explanation is substantively correct.

Fixture evals are provider-free and intentionally narrow. Packet cases assert the exact sorted blocker set plus `ready` or `blocked`; Action cases assert the exact sorted violation set plus both `conclusion` and `passed` or `failed`. They do not snapshot the complete response object.

JSON Schema validation is test/CI-only. `requirements-dev.txt` installs `jsonschema` for `tests/test_schema.py`; the package's runtime dependency list remains empty. Python validators continue to own stateful semantics such as material snapshots, repository identity, Git receipts, policy conflicts, and remote-write readiness.

The repository dogfoods the policy and workflow in [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`SECURITY.md`](../SECURITY.md), [`.reviewworthy/policy.toml`](../.reviewworthy/policy.toml), and [`examples/contribution/README.md`](../examples/contribution/README.md). Branch protection and required-check settings are external maintainer controls, not repository-file side effects.
