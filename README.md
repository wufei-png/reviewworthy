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
reviewworthy brief render .reviewworthy/project-brief.json --output project-brief.md
reviewworthy candidate search --repo OWNER/REPO --query "keyword"
reviewworthy candidate init --repository OWNER/REPO
reviewworthy candidate validate .reviewworthy/candidates.json
reviewworthy contract init --output .reviewworthy/contribution-contract.json
reviewworthy risk assess MANIFEST.json
reviewworthy packet validate .reviewworthy/contribution.json
reviewworthy action check .reviewworthy/contribution.json
reviewworthy disclosure render --packet .reviewworthy/contribution.json
reviewworthy eval run
reviewworthy remote plan ...
reviewworthy remote create ... --confirm-operation-id rw-...
```

The CLI and Skill share a Contribution Packet. The GitHub Action is read-only and checks objective evidence. The remote adapter uses the user's authenticated `gh` CLI and refuses to write unless the current rendered operation ID is explicitly confirmed.

## Workflow contract

```text
Issue-backed entry ─┐
                    ├─ contribution basis → contract → implementation
Discovery entry ────┘                                      ↓
                         verification → Orientation → Assessment → narrative preview → PR
```

Discovery evidence may serve as the contribution basis when repository policy allows it. Speculative work still needs a project signal. Both entries use the same implementation and verification path.

Every node records a result. Review depth is `standard` or `heightened`; risk signals and user escalation can raise it, never lower it. Security issues, policy conflicts, irreversible changes, and unverifiable results are independent hard-stops.

Understanding is material-bound: Orientation explains the contract, final Diff, verification evidence, and policy result; Assessment asks new questions. A material change invalidates the prior Assessment.

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

Unknown policy enters Conservative mode. The CLI preserves human approval and disclosure requirements. The Action reports unknown policy without failing by default because it is a read-only reporter, not the project decision-maker.

## Remote writes

Remote writes are opt-in and use a two-step local protocol:

1. Render the exact target, title, Body, permissions, and stable operation ID with `remote plan`.
2. Run `remote create` with that exact operation ID.

The operation ID is embedded in a hidden Body marker. Before creating an Issue or Pull Request, Reviewworthy searches for the marker. An uncertain network result must be reconciled before retrying; the tool never blindly creates a duplicate.

After a successful create, an ignored local operation receipt under `.reviewworthy/local/operations/` also protects immediate retries during GitHub's read-after-write delay.

The first release does not create review comments, close PRs, merge changes, or use an LLM as an Action gatekeeper.

## Documents

- [Domain language](./CONTEXT.md)
- [Agent Skill](./SKILL.md)
- [Project brief and orientation](./references/onboarding-contract.md)
- [Candidate evidence matrix](./references/candidate-scoring.md)
- [Contribution Contract](./references/contribution-contract.md)
- [AI disclosure](./references/ai-disclosure.md)
- [Fixture evaluations](./references/evaluation.md)
- [Policy discovery reference](./references/policy-discovery.md)
- [Understanding gate reference](./references/understanding-gate.md)
- [Remote write reference](./references/remote-writes.md)
- [Architecture decisions](./docs/adr/)

## Status

This is an early open-source foundation released under the [MIT License](./LICENSE). The current slice adds deterministic project facts, evidence-first candidate menus, standalone Contribution Contracts, policy-aware disclosure records, and provider-free fixture evaluations. Richer provider adapters and deeper project-specific onboarding remain later slices.
