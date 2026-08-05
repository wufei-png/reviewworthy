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

1. Identify the repository and read `README`, `CONTRIBUTING`, security guidance, templates, and relevant docs. Run `reviewworthy policy inspect .`.
2. Classify the entry as Issue-backed or Discovery. Run `reviewworthy candidate search --repo OWNER/REPO --query "..."` and inspect duplicate Issues/PRs before treating a candidate as actionable.
3. Record the contribution basis. Discovery evidence can qualify only when repository policy permits it; speculative improvements need a project signal.
4. Build a contribution contract: problem, non-goals, scope, invariants, design, alternatives, validation plan, Diff budget, risks, and success criteria.
5. Assess review depth with `reviewworthy risk assess`. Escalate when the user requests more scrutiny. Respect hard-stops independently.
6. Ask for approval of the contract before implementation. Re-plan if the implementation materially leaves the approved scope.
7. Implement the smallest coherent change. Record commands, exit codes, and verification evidence.
8. Prepare the exact final Diff and update the material snapshot. Run Orientation, then ask fresh Assessment questions. Regenerate stale Assessment after any material change.
9. Prepare the final PR title and Body. Always show the exact text. For heightened work or policy-required narrative, require the user's own motivation, trade-offs, and risks before AI copyediting.
10. Run `reviewworthy remote plan`. Only after the user confirms the displayed operation ID may the CLI create the requested Issue or formal Pull Request through `gh`.

## Stop outcomes

Prefer an honest result such as `STOP`, `NEEDS_MAINTAINER_SIGNAL`, `POLICY_CONFLICT`, `DUPLICATE_WORK`, or `NEEDS_MORE_LEARNING` over an unsolicited PR.

The deterministic CLI validates evidence and state. The Skill owns the dialog, teaching, candidate selection, contract approval, and narrative negotiation.
