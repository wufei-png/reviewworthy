---
name: maintainer-first-contribution
description: >
  Use a contributor-side workflow to prove that an AI-assisted contribution is
  needed, bounded, understood, and ready for maintainer review, while making
  only explicitly confirmed policy-compliant GitHub writes.
---

# Maintainer-first contribution

Use this contributor-side workflow whenever a user asks an Agent to make or publish an AI-assisted open-source contribution. Produce maintainer-friendly evidence, but do not treat maintainers as users of a second workflow.

## Non-negotiable boundaries

- Read the repository's contribution policy before planning or writing.
- Treat existing issues, maintainer requests, and policy-permitted reproducible discovery evidence as the contribution basis.
- Discovery candidates must be checked for duplicates before implementation.
- Record an explicit duplicate disposition (`exact_duplicate`, `potential_duplicate`, `related`, `not_duplicate`, `stale`, or `superseded`); the CLI records and enforces the disposition but does not infer it from similarity.
- Treat candidate recommendations as advisory evidence: `do_not_contribute` is a hard stop, while `issue_only` and `seek_maintainer_signal` need an explicit human-confirmed transition to `plan_directly`; the transition cannot bypass the required Issue or public Signal gate.
- Treat the composite Action's default as report-only. Select `evidence-enforce` only when the repository explicitly wants a blocking check over runner-owned Evidence Summary, Diff, identity, and base-policy facts.
- Issue-backed and Discovery entries converge into one contribution contract and one implementation/verification path.
- Record a result for every flow node; do not silently skip a node because a change is small.
- Calculate the `standard`, `heightened`, or explicitly educational `learning` review profile from risk signals and user choice. The user may raise the profile, never lower it.
- Stop on security issues, policy conflicts, irreversible changes, or unverifiable results.
- Treat independent hard-stops as higher priority than ordinary stage progress.
- For Heightened and Learning, run Orientation before Assessment. Assessment questions must not repeat the explanation and are bound to the semantic snapshot.
- Invalidate and regenerate Heightened/Learning Orientation and Assessment after a semantic change.
- Always show and obtain confirmation for the exact final PR title and Body.
- Never perform a GitHub write without an exact, current operation ID confirmation.

## Operating sequence

1. Start from the repository's existing Issue when one is available. Initialize the Git-private Packet, run `reviewworthy status --packet ... --json` (or `next`), then read `README`, `CONTRIBUTING`, security guidance, templates, and relevant docs. Run `reviewworthy policy inspect .` before relying on `.reviewworthy/policy.toml`. Re-run status after each deterministic transition instead of reconstructing readiness from prose.
2. Create `reviewworthy brief create` and complete its Skill/contributor-owned sections during Orientation; bind the brief to the repository identity and base SHA, and record hashes only for explicitly selected focus files. The deterministic source manifest is evidence, not an AI architecture claim.
3. For the default Issue-backed path, bind the canonical Issue to the Packet and use `reviewworthy issue verify --packet ... --record`. Verification proves the public record and repository identity; it does not infer maintainer approval.
4. Use Discovery only when no suitable Issue exists and repository policy permits it. Run `reviewworthy candidate search --repo OWNER/REPO --query "..."`, populate an evidence-first candidate menu, and inspect duplicate Issues/PRs before treating a candidate as actionable. Record the human/Skill-owned duplicate disposition; `exact_duplicate` and unresolved `potential_duplicate` remain blockers. Treat `do_not_contribute` as a hard stop. Record a structured Contribution Signal and verify its public reference, or record policy-permitted reproducible evidence, before implementation. A recommendation or candidate transition never substitutes for these basis gates.
5. Build a Contribution Contract with problem, non-goals, scope, invariants, design, alternatives, validation plan, Diff budget, risks, and success criteria. Validate it with `reviewworthy contract validate`; approval comes only after the selected basis has been bound into the Packet.
6. Assess the review profile with `reviewworthy risk assess`. Escalate when the user requests more scrutiny. Respect hard-stops independently.
7. Bind any confirmed Candidate Menu selection into the Packet, record the required human-confirmed transition when its recommendation is `issue_only` or `seek_maintainer_signal`, then ask for approval of the Contract before implementation. Re-plan if the implementation materially leaves the approved scope.
8. Implement the smallest coherent change. When it is complete, run `reviewworthy diff bind --root . --packet ... --base BASE --head HEAD`. Binding requires the selected head to be the current clean HEAD, checks the approved scope and Diff budget, updates the existing implementation result and semantic snapshot, and routes `status/next` into verification. It does not create an `implementation_ready` field or another persisted milestone.
9. Run the Packet's named verification checks through `reviewworthy verify run` so `argv`, `cwd`, exit code, clean-worktree proof, and the tested `head_sha` are recorded; stdout/stderr hashes are audit data only. Record the AI-assistance stages and human verification record.
10. Review the exact bound Diff. Standard requires the light Ownership Check covering problem, scope, verification, and risks. Heightened and Learning additionally record and validate Orientation, then ask fresh Assessment questions across behavior, invariants, tests, flow, trade-offs, failures, and regressions. The CLI validates rubric structure and evidence presence, not whether an answer is substantively correct. Regenerate stale records after any semantic change.
11. Render disclosure with `reviewworthy disclosure render` according to normalized policy. Prepare the final PR title and Body and always show the exact text. For heightened work or policy-required narrative, require the user's own motivation, trade-offs, and risks before AI copyediting.
12. Run `reviewworthy remote plan`. For a Pull Request, it recomputes the merge-base contribution Diff and requires exact agreement across all public Diff identity fields. The Packet repository identity and live Issue identity must also match, and the PR Body must contain the canonical supporting Issue URL. Reviewworthy appends a human-readable evidence overview plus the machine-readable Evidence Summary. “Ready for maintainer review” is contributor-workflow completion, not maintainer approval or a score. Only after the user confirms the exact displayed operation ID may the CLI write through `gh`.
13. Keep `action.yml` read-only and in report mode unless the repository explicitly opts into `evidence-enforce`. The Action reads only the public machine Evidence Summary and base-tree policy, never the private Packet, and never comments. Use fixture evals with exact blocker/violation sets and conclusion assertions. Do not infer branch protection or required-check configuration from repository files.

## Stop outcomes

Prefer an honest result such as `STOP`, `NEEDS_MAINTAINER_SIGNAL`, `POLICY_CONFLICT`, `DUPLICATE_WORK`, or `NEEDS_MORE_LEARNING` over an unsolicited PR.

The deterministic CLI validates evidence and state. The Skill owns the dialog, teaching, candidate selection, contract approval, and narrative negotiation.
