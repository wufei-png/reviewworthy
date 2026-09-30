# 04 — 实现前 Packet 操作接口

Design status: **Approved (2026-09-30)**. Execution status: **Not started**.

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

- Status: Not started.
- Comparison base and commits: —
- Checks/results: —
- Review findings and decisions: —
- Fixes and rechecks: —
- Final interfaces/deviations/unverified items: —
