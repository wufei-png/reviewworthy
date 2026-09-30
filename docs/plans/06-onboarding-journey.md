# 06 — Onboarding 与完整旅程

Design status: **Approved (2026-09-30)**. Execution status: **Not started**.

Earlier foundations (ordering reference): 01–05。

Follow the [shared queue](./recovery-and-workflow-queue.md), execute only 06. Other session plans need not be pre-read. Commands introduced here are planned interfaces, not baseline capabilities.

Read: `brief.py`, repository identity helpers, 01–05's final CLI interfaces, `workflow.py`, `SKILL.md`, `README.md`, `references/onboarding-contract.md`, `examples/contribution/README.md`, `tests/test_e2e.py` and workflow/Brief tests.

## Stages

1. `start --root ... --contribution-id ... --issue URL --focus PATH` — collect policy/repository/Brief facts, initialize or reuse Git-private artifacts, bind/verify the explicit Issue read-only, and return artifact paths plus the next action. Keep the Brief source-manifest-only; preserve human-owned sections. A failed/interrupted start can retry without overwriting an approved Packet or contributor content. No new session-state file or provider write.
2. Next-step integration and hermetic journeys — reuse existing node/readiness logic. At the remote boundary, `next` may suggest reconciliation for matching current operation state using its existing command/reason output; the Packet's workflow stage remains derived, not replaced by operation history. Do not let unrelated or malformed operation files silently rewrite Packet readiness. Missing human decisions produce clear decision hints, not fabricated values or commands with executable ellipses.
3. Current quickstart/Skill/reference and final distribution checks — make the normal Issue-backed path discoverable, retain advanced Discovery, and document the actual interfaces and recovery examples. Update the execution records and applicable changelog/release evidence honestly.

## Acceptance

- Hermetic Python, Node-shaped and Go-shaped Git repositories complete start → basis → approved Contract → committed implementation → clean Diff bind → named verification → ownership/disclosure/narrative confirmation → remote plan, with no direct Packet edits.
- Provider facts are injected through a fake transport; real Git and actual subprocess receipt binding are exercised. Tooling-shape fixtures verify discovery and workflow contracts, not unexecuted npm/Go toolchains or live provider rights.
- Test each stage's `next`, repetition, interrupted initialization, a policy hard stop, material changes after approval/verification/confirmation, and recovery of a pending remote operation through 01.
- No remote object is created by start, status, next, Brief generation or remote plan. Every suggested executable command exists and every unresolved human choice remains visible.
- Full tests/evals/compile/schema/Action smoke and wheel clean-install checks pass, or missing prerequisites are clearly recorded without marking the session complete.

## Review and execution record

Use implement-in-stages for scoped local commits, then delegated-change-review for one fresh read-only review of this session's full change. Record the comparison base, findings, accepted/rejected decisions, verified fixes and unverified items. Complete the relevant rechecks after each accepted fix before marking this session complete.

Update this plan and the queue together after implementation/review; do not start the next session automatically.

- Status: Not started.
- Comparison base and commits: —
- Checks/results: —
- Review findings and decisions: —
- Fixes and rechecks: —
- Final interfaces/deviations/unverified items: —
