# 05 — 验证、Ownership 与公开叙述

Design status: **Approved (2026-09-30)**. Execution status: **Complete (2026-09-30)**.

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

- Status: Complete (2026-09-30). Only session 05 was executed; 06 remains not started.
- Comparison base: `48ac1e732a0776dcd7d9925cca8b222830dc0f44`.
- Stage commits:
  1. `1987d6c` — synchronize implementation/verification results and downstream semantic invalidation; 123 Packet/CLI/workflow/schema checks passed.
  2. `84e2af0` — typed Ownership/AI recording, explicit claims, policy checks and confirmation resets; 153 focused checks including docs/artifacts passed.
  3. `32d0282` — exact narrative record/preview/confirm, public projection and actionable next steps; 157 focused checks passed, including a CLI-only Standard journey from init through real Git binding/local execution to remote plan, and Heightened/Learning phase-order tests.
- Complete-change checks: initially 325 unit tests passed; after both review fixes, 327 unit tests passed on Python 3.11.5. All 11 eval fixtures, compileall, staged whitespace checks and full comparison-range diff checks passed. Documentation/artifact checks were rerun for record closure.
- One fresh read-only delegated review inspected the complete `48ac1e7..32d0282` session diff and independently passed 56 focused checks. Both P2 findings were independently reproduced and accepted; no findings were rejected:
  - Partial required verification generated `not_recorded` with a positive receipt count, violating the existing public Summary contract and breaking preview/remote plan.
  - An unstable optional receipt blocked verification while `next` incorrectly requested an already existing required plan rather than routing cleanup and rerun of that check.
- Fixes and rechecks:
  - `a56c2f2` — incomplete public verification uses the existing `not_recorded`/zero-count projection. Added schema/rendering and CLI preview/remote-plan regressions; 53 focused checks passed.
  - `c70505c` — route blocking optional receipts to their check IDs with clean-worktree/bound-HEAD recovery guidance. Added CLI failure-to-recovery regression; 79 focused checks passed.
- Final interfaces: `packet ownership record --packet ... --input FILE`; `packet ai record --packet ... --input FILE`; `packet narrative record --packet ... --title ... --body-file ... [--human-expression-file FILE]`; `packet narrative preview --packet ... [--output FILE --force]`; `packet narrative confirm --packet ... --human-confirmed`. All support `--json`. Existing input sections and artifact/schema versions remain in use; no second business-fact envelope, freshness field, or confirmation challenge was added.
- Material contribution inputs invalidate their dependent human evidence; Ownership changes preserve actual receipts, while audit-only receipt timestamp/output-hash updates preserve readiness. Current receipt identity includes command, HEAD, provenance and worktree proof in the semantic projection. A historical understanding snapshot may require re-recording against current CLI-maintained evidence. Changed Orientation resets Assessment; final confirmation explicitly approves current prose/disclosure without inventing stage human verification. Remote input title/Body equality now includes whitespace. Preview's exported raw Body is only a convenience; remote plan still recomputes Git identity and renders the operation marker.
- Unverified items and limits: Git/provider journeys use hermetic repositories and injected provider evidence; no live GitHub writes, runner execution, push, wheel/release checks or Python 3.12/3.13 execution. CLI structure/evidence checks do not prove human comprehension or truthfulness of disclosure. Final documentation commit closes this record and the shared queue.
