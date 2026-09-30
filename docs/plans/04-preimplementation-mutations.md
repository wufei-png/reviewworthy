# 04 — 实现前 Packet 操作接口

Design status: **Approved (2026-09-30)**. Execution status: **Complete (2026-09-30)**.

Earlier foundations (ordering reference): 02。

Follow the [shared queue](./recovery-and-workflow-queue.md), execute only 04. Other session plans need not be pre-read. Commands introduced here are planned interfaces, not baseline capabilities.

Read: `packet.py` format/semantic/readiness/result helpers, `candidate.py` bind/transition, `contract.py`, `risk.py`, the corresponding CLI branches, `workflow.py`, `references/contribution-contract.md`, schemas and tests.

## Interface and semantic contract

Provide typed commands, planned as:

- `packet policy bind --root ... --packet ...`: obtains policy itself; the Agent does not reconstruct its output.
- `packet basis record --packet ... --issue URL` or `--signal FILE`: records identity/basis using existing fields; external evidence is verified through existing read-only commands. Preserve candidate gates. Issue-backed entry does not need a fabricated Candidate Menu solely for wiring.
- `packet contract bind --packet ... --contract FILE`, then `packet contract approve --packet ... --human-confirmed`: approval occurs against the current embedded Contract after a valid basis and policy have been established. The CLI computes `contract_sha256`; an Agent never supplies it. Standalone Contract init/validate/render continue to work; do not require a second approved copy or an atomic two-file approval transaction.
- `packet review record --packet ... --input FILE`: consumes the existing risk/review data, permits raising the profile, and never downgrades required scrutiny or removes independent hard stops without a valid explicit decision.
- `packet verification plan --packet ... --input FILE`: consumes the current plan/check shape, computes its digest, preserves exact argv/cwd/required semantics and invalidates affected receipts/results.

Inputs may use existing section JSON or simple domain flags, not a new patch-envelope schema. Reject attempts to write arbitrary snapshots, receipts, provider verification, approvals or result records through a generic patch interface.

One mutation helper/seam maintains atomic Packet replacement, snapshots, affected node results and downstream invalidation. Allow structurally valid incomplete Packets to progress; do not require final readiness before a command can repair an earlier stage. A changed basis invalidates Contract approval; changed Contract fields require approval again. Preserve stale evidence for explanation or reset it explicitly, but never make old approvals/receipts/understanding appear current by simply assigning a new hash.

## Stages

1. Policy/basis recording plus shared mutation/result rules — focused Packet/workflow/CLI tests.
2. Contract bind and human approval — tests for changed scope/design, missing basis and repeated identical input.
3. Review profile and verification-plan recording — tests for escalation, hard stops and stale plans/receipts.
4. Update `next` and active guidance for these delivered commands — executable known-input suggestions; decision hints when required human content is absent.

## Acceptance

From `packet init`, every pre-implementation prerequisite can be written through CLI domain operations with no manual Packet edit. Candidate recommendations still are not authorization. Existing external Signal and Issue identity checks remain effective. Identical updates do not needlessly invalidate approvals; material changes cannot preserve readiness. No command autoapproves a Contract or lowers review depth. Field payloads/hash computation are not duplicated across artifacts by the new interface.

## Review and execution record

Use implement-in-stages for scoped local commits, then delegated-change-review for one fresh read-only review of this session's full change. Record the comparison base, findings, accepted/rejected decisions, verified fixes and unverified items. Complete the relevant rechecks after each accepted fix before marking this session complete.

Update this plan and the queue together after implementation/review; do not start the next session automatically.

- Status: Complete (2026-09-30). Only session 04 was executed; no push, release, remote object creation or mutation canary.
- Comparison base: `eb329da` (`eb329da..d28abf4` was the full delegated-review target).
- Stage commits:
  1. `df7c515` — typed policy/basis operations, shared atomic Packet replacement and result/invalidation maintenance; existing candidate bind/transition and Issue verification recording use that seam. 109 focused Packet/mutation/workflow/CLI/schema tests passed.
  2. `1556bce` — Contract field binding and explicit human approval of the embedded Contract; source approval is not imported and the standalone artifact is not changed. 137 focused tests including artifact validation passed.
  3. `0d4442d` — monotonic review recording and exact verification-plan recording with CLI-owned digest. 116 focused tests passed.
  4. `d28abf4` — current `next` suggestions, active Skill/references/README and a CLI-only pre-implementation journey. 101 focused tests passed.
- Checks/results: Python 3.11.5 passed 313 tests before review and 315 tests after the accepted fixes and final idempotence audit with `PYTHONPATH=src python -m unittest discover -s tests -v`. All 11 eval fixtures passed before and after fixes. `python -m compileall -q src tests` and complete-range `git diff --check eb329da` passed. Schema checks used the available test-only `jsonschema` dependency; runtime dependencies and artifact versions did not change. The journey uses a real temporary Git repository and a fake read-only provider; it is not live-provider evidence.
- Review findings and decisions: one fresh read-only subagent used `review-agent` and inspected the full session diff. It independently passed 124 focused tests and reported two P2 findings. Both were independently reproduced and accepted; no rejected findings. The first found that schema-valid review sections can omit optional lists; the second found that verified PR/Discussion Signals supplied an immutable ID that basis binding failed to retain. No second delegated review was run after fixes; regression checks verified the accepted fixes.
- Fixes and rechecks:
  - `d7c36f3` — initialize absent optional review lists while rejecting malformed present values; 82 mutation/Packet/workflow/schema tests passed, including the CLI failure-without-write regression.
  - `a5a6745` — final audit found that filling absent optional review lists on an identical minimal input unnecessarily reset receipts. Preserve absent empty lists; regression assertions verify identical-input receipt/understanding preservation. 83 mutation/Packet/workflow/schema tests passed.
  - `c4fa93a` — import an absent immutable repository ID from validated external Signal evidence and preserve identity-mismatch rejection; 72 mutation/Signal/CLI/schema tests passed, including PR and Discussion cases. Final full regression/eval/compile/diff checks passed after these fixes.
- Final interfaces:
  - `packet policy bind --root ROOT --packet PACKET [--json]` collects policy itself.
  - `packet basis record --packet PACKET (--issue URL | --signal FILE) [--repository OWNER/REPO] [--json]` records the existing basis fields. Public references infer an absent slug; verified external Signal evidence supplies an absent immutable ID. Existing candidate recommendation/duplicate gates remain attached, and existing read-only Issue/Signal verification remains required.
  - `packet contract bind --packet PACKET --contract FILE [--json]` binds the standalone Contract fields; identical fields preserve current approval.
  - `packet contract approve --packet PACKET --human-confirmed [--json]` checks established policy, valid verified basis and candidate/hard-stop gates, then computes the current embedded Contract hash. No second approved copy is required.
  - `packet review record --packet PACKET --input FILE [--json]` accepts the existing review section or `risk assess --json` result, merges signals/stops and only raises scrutiny. Clearing hard stops is outside this recording interface.
  - `packet verification plan --packet PACKET --input FILE [--json]` accepts the existing plan/check shape and computes its digest; argv/cwd/required retain their exact semantics. Changed plans reset receipts and affected results.
- Invalidation: material basis/policy changes reset Contract approval; material Contract edits require approval again and reset the implementation binding. Review/plan changes preserve Contract approval and implementation binding but reset affected verification, Ownership, narrative confirmation and understanding. Old understanding content/material hashes remain for explanation with status reset; no completed record is made current by assigning a new hash. Identical semantic inputs and provider timestamp-only refreshes preserve current evidence.
- Deviations: added optional `basis record --repository` because a local Signal has no public URL from which to infer the Packet's missing identity. This uses the existing repository fields rather than a new envelope. `next` treats the default skeleton's empty slug as incomplete and asks for a missing verification plan before suggesting implementation; absent human content/approval stays a decision hint.
- Unverified items/limits: Python 3.12/3.13, live GitHub/provider/runner behavior and wheel/release installation were not exercised locally in 04. Existing remote race/visibility limits remain. Human confirmation remains a contributor claim; no new authentication or authority inference was added. Session 05/06 were not started.
