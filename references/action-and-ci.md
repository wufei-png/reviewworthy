# Action, eval, and Schema CI

The composite Action is intentionally read-only. Its default `report` mode preserves the conservative behavior used by existing consumers: a missing Packet or unknown policy/evidence is reported and does not fail the check. A repository that explicitly chooses enforcement can set `mode: enforce`, or turn on `require-packet`, `require-current-diff`, and `fail-on-unknown` individually.

`enforce` means:

- a Contribution Packet must exist and be valid;
- changed-file evidence must come from the current event/input rather than only the Packet;
- unknown policy or deterministic evidence becomes a violation.

The Action still does not infer maintainer approval, call `gh`, create Issues/PRs, or decide whether a human explanation is substantively correct.

Fixture evals are provider-free and intentionally narrow. Packet cases assert the exact sorted blocker set plus `ready` or `blocked`; Action cases assert the exact sorted violation set plus both `conclusion` and `passed` or `failed`. They do not snapshot the complete response object.

JSON Schema validation is test/CI-only. `requirements-dev.txt` installs `jsonschema` for `tests/test_schema.py`; the package's runtime dependency list remains empty. Python validators continue to own stateful semantics such as material snapshots, repository identity, Git receipts, policy conflicts, and remote-write readiness.

The repository dogfoods the policy and workflow in [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`SECURITY.md`](../SECURITY.md), [`.reviewworthy/policy.toml`](../.reviewworthy/policy.toml), and [`examples/contribution/README.md`](../examples/contribution/README.md). Branch protection and required-check settings are external maintainer controls, not repository-file side effects.
