# 05 — 验证、Ownership 与公开叙述

Design status: **Approved (2026-09-30)**. Execution status: **Not started**.

Earlier foundations (ordering reference): 04。

Follow the [shared queue](./recovery-and-workflow-queue.md), execute only 05. Other session plans need not be pre-read. Commands introduced here are planned interfaces, not baseline capabilities.

Read: `verify run`/`diff bind`/understanding CLI handlers, `git.py` receipt semantics, `packet.py`, `understanding.py`, `disclosure.py`, `evidence.py`, relevant references/schemas and tests.

## Contract

- Synchronize implementation/verification flow-node results from actual Diff binding and current required receipts, including failed, unstable, stale and partially completed verification. Do not accept Agent-supplied receipts or a repeated “tests passed” declaration as a substitute.
- Add `packet ownership record --packet ... --input FILE` using existing problem/scope/verification/risks content and explicit human/Skill check outcome. CLI checks structure/evidence, not truthfulness of answers.
- Add `packet ai record --packet ... --input FILE` using the existing assistance/disclosure shape. Preserve explicit human_verified/human_confirmed claims and policy-required stages/locations. Editing disclosure text/locations clears its prior confirmation. Do not automatically claim the human reviewed every stage.
- Add `packet narrative record --packet ... --title ... --body-file ...` and `packet narrative confirm --packet ... --human-confirmed`. Use existing narrative/human_expression fields. Recording changes clears final confirmation; confirmation requires complete current content/disclosure and explicit human approval after preview. Coordinate disclosure confirmation through explicit existing human claims, without a new hash/challenge protocol or another mandatory artifact.
- Keep exact public title/body/Issue-link/disclosure gates. Save a private body file if needed for subsequent remote commands; it is an implementation convenience, not a new source of authority. Preview the same current text that will be planned.
- Material basis/Contract/Diff/plan/review/ownership changes invalidate appropriate verification, ownership, understanding and narrative readiness. Do not invalidate a receipt for an unrelated audit timestamp or output-hash change. Reuse existing semantic projection rules. Add conservative explicit invalidation for claims not already snapshot-bound; do not add a parallel freshness field.

## Stages

1. Diff/verification result synchronization and downstream invalidation — receipt/head/worktree and failure tests.
2. Ownership and AI/disclosure recording — content, policy and confirmation-reset tests.
3. Narrative record/preview/confirm and `next` — exact-body matching, human expression and stale-confirmation tests.

## Acceptance

A Standard journey reaches remote plan through CLI mutations; every required flow node has justified evidence. Heightened/Learning still require current Orientation before Assessment. Later edits require the appropriate human reapproval; unrelated audit-only edits do not. Re-running a failed or required check updates the derived result truthfully. CLI never invents comprehension, provider authority or disclosure verification.

## Review and execution record

Use implement-in-stages for scoped local commits, then delegated-change-review for one fresh read-only review of this session's full change. Record the comparison base, findings, accepted/rejected decisions, verified fixes and unverified items. Complete the relevant rechecks after each accepted fix before marking this session complete.

Update this plan and the queue together after implementation/review; do not start the next session automatically.

- Status: Not started.
- Comparison base and commits: —
- Checks/results: —
- Review findings and decisions: —
- Fixes and rechecks: —
- Final interfaces/deviations/unverified items: —
