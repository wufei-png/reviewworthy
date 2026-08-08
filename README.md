# Reviewworthy

Reviewworthy is a maintainer-first workflow for human-owned, AI-assisted open-source contributions.

It does not optimize for the number of generated pull requests. It records why a contribution is wanted, checks repository policy, keeps a bounded contribution contract, preserves verification evidence, tests contributor understanding, and makes remote writes explicit and idempotent.

The project brand is **Reviewworthy**. The portable Agent Skill is **`maintainer-first-contribution`**.

## Current slice

The repository currently provides an alpha, standard-library-only Python CLI with these deterministic primitives:

```text
reviewworthy packet init --output .reviewworthy/contribution.json
reviewworthy policy inspect [REPOSITORY]
reviewworthy brief create --output .reviewworthy/project-brief.json --focus src/relevant_file.py
reviewworthy brief validate .reviewworthy/project-brief.json --root .
reviewworthy brief render .reviewworthy/project-brief.json --output project-brief.md
reviewworthy candidate search --repo OWNER/REPO --query "keyword"
reviewworthy candidate init --repository OWNER/REPO
reviewworthy diff capture --root . --base BASE --head HEAD
reviewworthy verify run --root . --head HEAD --json -- python -m unittest
reviewworthy candidate validate .reviewworthy/candidates.json
reviewworthy signal init --kind maintainer-request --reference https://github.com/OWNER/REPO/issues/123 --published
reviewworthy signal validate .reviewworthy/contribution-signal.json
reviewworthy signal verify .reviewworthy/contribution-signal.json
reviewworthy signal publish plan .reviewworthy/contribution-signal.json --repo OWNER/REPO --title "Candidate request" --body-file signal.md
reviewworthy candidate select .reviewworthy/candidates.json --candidate-id candidate-001 --confirm
reviewworthy candidate bind --menu .reviewworthy/candidates.json --packet .reviewworthy/contribution.json
reviewworthy candidate transition --packet .reviewworthy/contribution.json --from issue_only --to plan_directly --reason "Human-confirmed reason" --confirm
reviewworthy contract init --output .reviewworthy/contribution-contract.json
reviewworthy risk assess MANIFEST.json
reviewworthy packet validate .reviewworthy/contribution.json
reviewworthy issue verify --packet .reviewworthy/contribution.json --record
reviewworthy understanding record .reviewworthy/contribution.json --phase orientation --status passed --summary "..." --rubric behavior="..." --rubric invariant="..." --rubric test="..." --topic contract --topic diff --topic verification --topic policy
reviewworthy understanding validate .reviewworthy/contribution.json
reviewworthy action check .reviewworthy/contribution.json --mode report
reviewworthy action check .reviewworthy/contribution.json --mode enforce --root .  # in a pull_request Action context
reviewworthy disclosure render --packet .reviewworthy/contribution.json
reviewworthy eval run
reviewworthy remote plan ...
reviewworthy remote create ... --confirm-operation-id rw-...
```

The CLI and Skill share a Contribution Packet and a status-bearing Contribution Signal. Packets bind their evidence to a GitHub repository identity. Briefs record the local Git remote/default branch/base SHA and hash only explicitly named focus files; they do not invent symbols or dependency graphs. The GitHub Action is read-only and checks objective evidence. The remote adapter uses the user's authenticated `gh` CLI and refuses to write unless the current rendered operation ID is explicitly confirmed.

## Workflow contract

```text
Issue-backed entry ─┐
                    ├─ contribution basis → contract → implementation
Discovery entry ────┘                                      ↓
                         verification → Orientation → Assessment → narrative preview → PR
```

Discovery evidence may serve as the contribution basis when repository policy explicitly allows it. A selected Discovery or signal-backed contribution must record a valid Contribution Signal before implementation or remote readiness; it does not need maintainer confirmation. External signals must reference a public record and have a successful verification record, while reproducible evidence may remain unpublished. `signal verify` is read-only by default; `signal verify --record` persists the exact successful check for readiness. `signal publish` is an explicit, idempotent Issue write and never infers maintainer intent. A verified, pending Issue is sufficient for the Issue-backed path; normalized `not planned` blocks progression, while an exact normalized `duplicate` label is an independent blocker. `completed` and `reopened` do not block by themselves.

Candidate recommendations are evidence-backed guidance, not authorization. `do_not_contribute` is a hard stop. `issue_only` and `seek_maintainer_signal` may transition to `plan_directly` only through an explicit human-confirmed reason; that transition does not bypass the required Issue or public Signal verification gate.

Every node records a result. Review depth is `standard` or `heightened`; risk signals and user escalation can raise it, never lower it. Standard Understanding covers behavior, invariant, and test; heightened Understanding additionally records flow, tradeoffs, failures, and regressions. The CLI checks rubric categories, evidence shape, and material snapshots, but does not claim that an answer is correct. Security issues, policy conflicts, irreversible changes, and unverifiable results are independent hard-stops.

The contract must be explicitly approved before remote readiness. A confirmed Candidate Menu selection can be bound to a Packet with a menu snapshot, but it does not approve the Contract. Verification needs commands and evidence plus a Git-bound receipt: `provenance=cli_executed`, `exit_code=0`, `status=valid`, `argv`, repository-relative `cwd`, matching `head_sha`, stable `head_sha_before == head_sha == head_sha_after`, and clean worktree proof both before and after execution are hard fields; output hashes are audit-only. Orientation must pass before Assessment, and both phases are material-bound: Orientation explains the contract, basis, final Diff, verification evidence, and policy result; Assessment asks new questions. A material change invalidates the prior records.

## Local development

The runtime requires Python 3.11 or newer and has no third-party runtime dependencies.

```bash
python -m pip install --requirement requirements-dev.txt  # test/CI-only dependency
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m reviewworthy --version
```

To install the console script locally:

```bash
python -m pip install -e .
reviewworthy policy inspect .
```

## Policy discovery

Reviewworthy reads repository-authored policy documents first, including `README`, `CONTRIBUTING`, `SECURITY`, `AGENTS`, `.github` templates, and Markdown under `docs/`. An optional `.reviewworthy/policy.toml` supplies structured claims where documents are silent. Explicit negative statements become `false`; contradictions across sources produce `policy_conflict`, while opposed claims inside one source produce `policy_ambiguity`. Both are hard stops and are never silently overridden.

Unknown policy, including an explicit `allowed = "unknown"` claim, enters Conservative mode. The CLI preserves human approval and disclosure requirements. The Action reports incomplete/unknown policy without failing by default, except for independently deterministic prohibitions such as an explicit AI prohibition.

Policy inspection also emits claim records with `true`/`false`/`unknown` state and source line/excerpt hashes. Document provenance is tied to the exact matched claim; structured provenance is tied to the parsed TOML table/key rather than an unrelated same-named key. Structured policy fills silence and remains provenance-bearing; conflicting sources produce an unknown claim plus a hard-stop rather than an opaque automatic decision.

## Remote writes

Remote writes are opt-in and use a two-step local protocol:

1. Render the exact target, title, Body, permissions, and stable operation ID with `remote plan`.
2. Run `remote create` with that exact operation ID.

The operation ID is embedded in a hidden Body marker. Before creating an Issue or Pull Request, Reviewworthy searches for the marker. An uncertain network result must be reconciled before retrying; the tool never blindly creates a duplicate.

For Pull Requests, `remote plan/create` recomputes the contribution Diff from the selected base/head merge base. Packet `0.2` binds `comparison=merge_base`, `base_tip_sha`, `merge_base_sha`, `head_sha`, `patch_sha256`, `changed_files`, `additions`, and `deletions`; every field must match before the operation is rendered or written. Older Packet versions are rejected rather than reinterpreted.

For a policy-required Draft PR, the draft state is included in the operation ID and passed to `gh pr create --draft`. A pending local operation record is persisted immediately before a create; if the create or receipt persistence is uncertain, later retries stop for reconciliation instead of issuing another create. After a successful create, the ignored local operation receipt under `.reviewworthy/local/operations/` protects immediate retries during GitHub's read-after-write delay. Reviewworthy reads the actual remote PR head after create or remote reconciliation and again immediately before an Issue-note write; an unavailable or mismatched head becomes `remote_pr_head_unavailable` or `remote_pr_head_mismatch` and requires reconciliation. Issue-backed PRs contain the canonical Issue URL in the Body and add one exact PR URL note to that Issue; head uncertainty and note failures become `needs_reconciliation` without a second confirmation or another PR. Because GitHub exposes head reads and Issue comments as separate APIs, a head update concurrent with the comment POST remains a narrow provider race that receipts cannot make atomic.

The first release does not create review comments, Discussions, close PRs, merge changes, or use an LLM as an Action gatekeeper. The current signal slice records and gates the evidence; it does not yet wait for or fetch maintainer responses.

The repository also ships a read-only composite Action in [`action.yml`](./action.yml). Its default `report` mode runs the existing non-blocking check and reports missing packets or unknown evidence. An explicitly selected `enforce` mode is PR-only: it requires a real `pull_request` context, local base/head commit objects, a complete merge-base Diff recomputed through the shared Git capture implementation, exact agreement with the Packet's comparison/base-tip/merge-base/head/hash/files/counts, and a successful clean-worktree verification receipt bound to the current head. Hand-supplied `changed-files` are never a substitute in enforce mode; `require-packet`, `require-current-diff`, and `fail-on-unknown` remain available for report-mode consumers. It does not publish, comment, or infer maintainer approval. The Action never fetches missing objects: report mode describes unavailable PR evidence as unknown, while enforce mode fails closed. Consumers that use enforce should check out with `fetch-depth: 0`.

The runtime has no third-party dependencies. Schema validation is a test/CI-only concern: `requirements-dev.txt` installs `jsonschema`, and CI validates the portable schemas and generated test artifacts without adding it to the package runtime dependencies. Fixture evals assert exact blocker/violation sets and conclusion/result outcomes rather than whole response snapshots.

## Documents

- [Domain language](./CONTEXT.md)
- [Agent Skill](./SKILL.md)
- [Project brief and orientation](./references/onboarding-contract.md)
- [Candidate evidence matrix](./references/candidate-scoring.md)
- [Contribution Signal](./references/contribution-signal.md)
- [Contribution Contract](./references/contribution-contract.md)
- [AI disclosure](./references/ai-disclosure.md)
- [Fixture evaluations](./references/evaluation.md)
- [Action, eval, and Schema CI](./references/action-and-ci.md)
- [Policy discovery reference](./references/policy-discovery.md)
- [Understanding gate reference](./references/understanding-gate.md)
- [Remote write reference](./references/remote-writes.md)
- [Architecture decisions](./docs/adr/)

## Status

This is an early open-source foundation released under the [MIT License](./LICENSE). The current slice adds deterministic project facts, evidence-first candidate menus, status-bearing Contribution Signals, read-only GitHub reference verification, explicit Issue publication, candidate-to-packet binding and transition gates, structured understanding records, a read-only Action wrapper, standalone Contribution Contracts, policy-aware disclosure records, and provider-free fixture evaluations. Maintainer-response inference, Discussion publication, richer provider adapters, and deeper project-specific onboarding remain later slices.
