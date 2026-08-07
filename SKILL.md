---
name: maintainer-first-contribution
description: >
  Prepare a human-owned, reviewworthy open-source contribution by checking
  repository policy and duplicate work, recording a contribution basis and
  contract, implementing and verifying a bounded change, running a material
  understanding gate, reviewing the final PR narrative, and performing only
  explicitly confirmed policy-compliant GitHub writes.
---

# Maintainer-first contribution

Use this workflow whenever a user asks an Agent to make or publish an AI-assisted open-source contribution.

## Non-negotiable boundaries

- Read the repository's contribution policy before planning or writing.
- Treat existing issues, maintainer requests, and policy-permitted reproducible discovery evidence as the contribution basis.
- Discovery candidates must be checked for duplicates before implementation.
- Issue-backed and Discovery entries converge into one contribution contract and one implementation/verification path.
- Record a result for every flow node; do not silently skip a node because a change is small.
- Calculate `standard` or `heightened` review depth from risk signals. The user may raise depth, never lower it.
- Stop on security issues, policy conflicts, irreversible changes, or unverifiable results.
- Run Orientation before Assessment. Assessment questions must not repeat the explanation and are bound to the exact material snapshot.
- Invalidate and regenerate Assessment after a material change.
- Always show and obtain confirmation for the exact final PR title and Body.
- Never perform a GitHub write without an exact, current operation ID confirmation.

## Operating sequence

1. Identify the repository and read `README`, `CONTRIBUTING`, security guidance, templates, and relevant docs. Run `reviewworthy policy inspect .` before relying on `.reviewworthy/policy.toml`.
2. Create `reviewworthy brief create` and complete its Skill/contributor-owned sections during Orientation; the deterministic source manifest is evidence, not an AI architecture claim.
3. Classify the entry as Issue-backed or Discovery. Run `reviewworthy candidate search --repo OWNER/REPO --query "..."`, populate an evidence-first candidate menu, and inspect duplicate Issues/PRs before treating a candidate as actionable.
4. Record the contribution basis and structured Contribution Signal. Discovery candidates may be explored or have a local Issue/Discussion draft prepared while no public signal exists. Before implementation, publish the external Issue record or record valid reproducible evidence; use `reviewworthy signal verify` to check public references without inferring maintainer intent, then `--record` the successful result before remote readiness. Do not wait for a maintainer reply. Reproducible evidence also requires explicit policy allowance.
5. Build and approve a Contribution Contract: problem, non-goals, scope, invariants, design, alternatives, validation plan, Diff budget, risks, and success criteria. Validate it with `reviewworthy contract validate`.
6. Assess review depth with `reviewworthy risk assess`. Escalate when the user requests more scrutiny. Respect hard-stops independently.
7. Ask for approval of the contract before implementation. Re-plan if the implementation materially leaves the approved scope.
8. Implement the smallest coherent change. Capture the real Git diff and run verification through the CLI so `argv`, `cwd`, exit code, and the tested `head_sha` are recorded; stdout/stderr hashes are audit data only. Record the AI-assistance stages and human verification record.
9. Bind any confirmed Candidate Menu selection into the Packet before Contract approval. Prepare the exact final Diff and update the material snapshot. Record and validate Orientation, then ask fresh Assessment questions. Regenerate stale records after any material change.
10. Render disclosure with `reviewworthy disclosure render` according to normalized policy. Prepare the final PR title and Body and always show the exact text. For heightened work or policy-required narrative, require the user's own motivation, trade-offs, and risks before AI copyediting.
11. Run `reviewworthy remote plan`. The Packet repository identity and live Issue identity must match, and a PR Body must contain the canonical supporting Issue URL. Only after the user confirms the displayed operation ID and all signal/policy gates pass may the CLI create the requested Issue or formal Pull Request through `gh`. For an Issue-backed PR, the CLI then searches for the exact PR URL note, writes at most one such note, and records `needs_reconciliation` if the note cannot be written; it never creates a second PR.

## Stop outcomes

Prefer an honest result such as `STOP`, `NEEDS_MAINTAINER_SIGNAL`, `POLICY_CONFLICT`, `DUPLICATE_WORK`, or `NEEDS_MORE_LEARNING` over an unsolicited PR.

The deterministic CLI validates evidence and state. The Skill owns the dialog, teaching, candidate selection, contract approval, and narrative negotiation.
