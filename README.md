# Reviewworthy

Reviewworthy is a maintainer-first workflow for human-owned, AI-assisted open-source contributions.

It does not optimize for the number of generated pull requests. It records why a contribution is wanted, checks repository policy, keeps a bounded contribution contract, preserves verification evidence, tests contributor understanding, and makes remote writes explicit and idempotent.

The project brand is **Reviewworthy**. The portable Agent Skill is **`maintainer-first-contribution`**.

## Current slice

The repository currently provides an alpha, standard-library-only Python CLI with these deterministic primitives:

```text
reviewworthy packet init --output .reviewworthy/contribution.json
reviewworthy policy inspect [REPOSITORY]
reviewworthy brief create --output .reviewworthy/project-brief.json
reviewworthy brief validate .reviewworthy/project-brief.json --root .
reviewworthy brief render .reviewworthy/project-brief.json --output project-brief.md
reviewworthy candidate search --repo OWNER/REPO --query "keyword"
reviewworthy candidate init --repository OWNER/REPO
reviewworthy candidate validate .reviewworthy/candidates.json
reviewworthy signal init --kind maintainer-request --reference https://github.com/OWNER/REPO/issues/123
reviewworthy signal validate .reviewworthy/contribution-signal.json --require-confirmed
reviewworthy contract init --output .reviewworthy/contribution-contract.json
reviewworthy risk assess MANIFEST.json
reviewworthy packet validate .reviewworthy/contribution.json
reviewworthy action check .reviewworthy/contribution.json
reviewworthy disclosure render --packet .reviewworthy/contribution.json
reviewworthy eval run
reviewworthy remote plan ...
reviewworthy remote create ... --confirm-operation-id rw-...
```

The CLI and Skill share a Contribution Packet and a status-bearing Contribution Signal. The GitHub Action is read-only and checks objective evidence. The remote adapter uses the user's authenticated `gh` CLI and refuses to write unless the current rendered operation ID is explicitly confirmed.

## Workflow contract

```text
Issue-backed entry ─┐
                    ├─ contribution basis → contract → implementation
Discovery entry ────┘                                      ↓
                         verification → Orientation → Assessment → narrative preview → PR
```

Discovery evidence may serve as the contribution basis when repository policy explicitly allows it. A selected Discovery or signal-backed contribution must record a confirmed Contribution Signal before implementation or remote readiness. Both entries use the same implementation and verification path.

Every node records a result. Review depth is `standard` or `heightened`; risk signals and user escalation can raise it, never lower it. Security issues, policy conflicts, irreversible changes, and unverifiable results are independent hard-stops.

The contract must be explicitly approved before remote readiness. Verification needs commands and evidence, Orientation must pass before Assessment, and Assessment is material-bound: Orientation explains the contract, final Diff, verification evidence, and policy result; Assessment asks new questions. A material change invalidates the prior Assessment.

## Local development

The runtime requires Python 3.11 or newer and has no third-party runtime dependencies.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m reviewworthy --version
```

To install the console script locally:

```bash
python -m pip install -e .
reviewworthy policy inspect .
```

## Policy discovery

Reviewworthy reads repository-authored policy documents first, including `README`, `CONTRIBUTING`, `SECURITY`, `AGENTS`, `.github` templates, and Markdown under `docs/`. An optional `.reviewworthy/policy.toml` supplies structured claims where documents are silent. Contradictory claims produce a `policy_conflict` hard-stop; they are never silently overridden.

Unknown policy, including an explicit `allowed = "unknown"` claim, enters Conservative mode. The CLI preserves human approval and disclosure requirements. The Action reports incomplete/unknown policy without failing by default, except for independently deterministic prohibitions such as an explicit AI prohibition.

## Remote writes

Remote writes are opt-in and use a two-step local protocol:

1. Render the exact target, title, Body, permissions, and stable operation ID with `remote plan`.
2. Run `remote create` with that exact operation ID.

The operation ID is embedded in a hidden Body marker. Before creating an Issue or Pull Request, Reviewworthy searches for the marker. An uncertain network result must be reconciled before retrying; the tool never blindly creates a duplicate.

For a policy-required Draft PR, the draft state is included in the operation ID and passed to `gh pr create --draft`. A pending local operation record is persisted immediately before a create; if the create or receipt persistence is uncertain, later retries stop for reconciliation instead of issuing another create. After a successful create, the ignored local operation receipt under `.reviewworthy/local/operations/` protects immediate retries during GitHub's read-after-write delay.

The first release does not create review comments, Discussions, close PRs, merge changes, or use an LLM as an Action gatekeeper. The current signal slice records and gates the evidence; it does not yet wait for or fetch maintainer responses.

## Documents

- [Domain language](./CONTEXT.md)
- [Agent Skill](./SKILL.md)
- [Project brief and orientation](./references/onboarding-contract.md)
- [Candidate evidence matrix](./references/candidate-scoring.md)
- [Contribution Signal](./references/contribution-signal.md)
- [Contribution Contract](./references/contribution-contract.md)
- [AI disclosure](./references/ai-disclosure.md)
- [Fixture evaluations](./references/evaluation.md)
- [Policy discovery reference](./references/policy-discovery.md)
- [Understanding gate reference](./references/understanding-gate.md)
- [Remote write reference](./references/remote-writes.md)
- [Architecture decisions](./docs/adr/)

## Status

This is an early open-source foundation released under the [MIT License](./LICENSE). The current slice adds deterministic project facts, evidence-first candidate menus, status-bearing Contribution Signals, standalone Contribution Contracts, policy-aware disclosure records, and provider-free fixture evaluations. Maintainer-response waiting, richer provider adapters, and deeper project-specific onboarding remain later slices.
