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
- Record an explicit duplicate disposition (`exact_duplicate`, `potential_duplicate`, `related`, `not_duplicate`, `stale`, or `superseded`); the CLI records and enforces the disposition but does not infer it from similarity.
- Treat candidate recommendations as advisory evidence: `do_not_contribute` is a hard stop, while `issue_only` and `seek_maintainer_signal` need an explicit human-confirmed transition to `plan_directly`; the transition cannot bypass the required Issue or public Signal gate.
- Treat the composite Action's default as report-only. Select `evidence-enforce` only when the repository explicitly wants a blocking check over runner-owned Evidence Summary, Diff, identity, and base-policy facts.
- Issue-backed and Discovery entries converge into one contribution contract and one implementation/verification path.
- Record a result for every flow node; do not silently skip a node because a change is small.
- Calculate `standard`, `heightened`, or explicitly educational `learning` review depth from risk signals and user choice. The user may raise depth, never lower it.
- Stop on security issues, policy conflicts, irreversible changes, or unverifiable results.
- For Heightened and Learning, run Orientation before Assessment. Assessment questions must not repeat the explanation and are bound to the semantic snapshot.
- Invalidate and regenerate Heightened/Learning Orientation and Assessment after a semantic change.
- Always show and obtain confirmation for the exact final PR title and Body.
- Never perform a GitHub write without an exact, current operation ID confirmation.

## Operating sequence

1. Run `reviewworthy status --packet ... --json` (or `next`) when a Packet exists, then identify the repository and read `README`, `CONTRIBUTING`, security guidance, templates, and relevant docs. Run `reviewworthy policy inspect .` before relying on `.reviewworthy/policy.toml`. Re-run status after each deterministic transition instead of reconstructing readiness from prose.
2. Create `reviewworthy brief create` and complete its Skill/contributor-owned sections during Orientation; bind the brief to the repository identity and base SHA, and record hashes only for explicitly selected focus files. The deterministic source manifest is evidence, not an AI architecture claim.
3. Classify the entry as Issue-backed or Discovery. Run `reviewworthy candidate search --repo OWNER/REPO --query "..."`, populate an evidence-first candidate menu, and inspect duplicate Issues/PRs before treating a candidate as actionable. Record the human/Skill-owned duplicate disposition; `exact_duplicate` and unresolved `potential_duplicate` remain blockers, while `related`, `not_duplicate`, `stale`, and `superseded` do not automatically block (record `superseded_by` when applicable). Treat `do_not_contribute` as a hard stop. For `issue_only` or `seek_maintainer_signal`, record the human-confirmed reason before transitioning to `plan_directly`.
4. Record the contribution basis and structured Contribution Signal. Discovery candidates may be explored or have a local Issue/Discussion draft prepared while no public signal exists. Before implementation, publish the external Issue record or record valid reproducible evidence; use `reviewworthy signal verify` to check public references without inferring maintainer intent, then `--record` the successful result before remote readiness. Do not wait for a maintainer reply. Reproducible evidence also requires explicit policy allowance. A candidate transition never substitutes for these Issue/Signal gates.
5. Build a Contribution Contract with problem, non-goals, scope, invariants, design, alternatives, validation plan, Diff budget, risks, and success criteria. Validate it with `reviewworthy contract validate`; approval comes only after the selected basis has been bound into the Packet.
6. Assess review depth with `reviewworthy risk assess`. Escalate when the user requests more scrutiny. Respect hard-stops independently.
7. Bind any confirmed Candidate Menu selection into the Packet, record the required human-confirmed transition when its recommendation is `issue_only` or `seek_maintainer_signal`, then ask for approval of the Contract before implementation. Re-plan if the implementation materially leaves the approved scope.
8. Implement the smallest coherent change. Capture the complete real Git Diff and run verification through the CLI so `argv`, `cwd`, exit code, clean-worktree proof, and the tested `head_sha` are recorded; stdout/stderr hashes are audit data only. Record the AI-assistance stages and human verification record.
9. Prepare the exact final Diff and update the semantic snapshot. Standard requires the light Ownership Check covering problem, scope, verification, and risks. Heightened and Learning additionally record and validate Orientation, then ask fresh Assessment questions across behavior, invariants, tests, flow, trade-offs, failures, and regressions. The CLI validates rubric structure and evidence presence, not whether an answer is substantively correct. Regenerate stale records after any semantic change.
10. Render disclosure with `reviewworthy disclosure render` according to normalized policy. Prepare the final PR title and Body and always show the exact text. For heightened work or policy-required narrative, require the user's own motivation, trade-offs, and risks before AI copyediting.
11. Run `reviewworthy remote plan`. For a Pull Request, it recomputes the merge-base contribution Diff and requires exact agreement across `comparison`, `base_tip_sha`, `merge_base_sha`, `head_sha`, `subject_digest`, `fingerprint_algorithm`, `changed_files`, `additions`, and `deletions`; the Packet repository identity and live Issue identity must also match, and a PR Body must contain the canonical supporting Issue URL plus the current Evidence Summary. Only after the user confirms the displayed operation ID and all signal/policy gates pass may the CLI create the requested Issue or formal Pull Request through `gh`. For an Issue-backed PR, the CLI then searches for the exact PR URL note, writes at most one such note, and records `needs_reconciliation` if the note cannot be written; it never creates a second PR.
12. For maintainer-side automation, keep `action.yml` in report mode unless the repository explicitly opts into `evidence-enforce`; the Action reads only the public Evidence Summary and base-tree policy, never the private Packet. Use fixture evals with exact blocker/violation sets and conclusion assertions, and use JSON Schema only as a test/CI structural check. Dogfood this Skill against the repository's own `CONTRIBUTING.md`, `SECURITY.md`, `.reviewworthy/policy.toml`, and example contribution. Do not infer branch protection or required-check configuration from these files.

## Stop outcomes

Prefer an honest result such as `STOP`, `NEEDS_MAINTAINER_SIGNAL`, `POLICY_CONFLICT`, `DUPLICATE_WORK`, or `NEEDS_MORE_LEARNING` over an unsolicited PR.

The deterministic CLI validates evidence and state. The Skill owns the dialog, teaching, candidate selection, contract approval, and narrative negotiation.
