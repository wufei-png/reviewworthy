# Reviewworthy implementation plan — 2026-09-30

Design status: **Approved by the user on 2026-09-30**.

The approved plan is split into a [shared queue](../docs/plans/recovery-and-workflow-queue.md) and six independent session plans. Read the queue and only the selected plan; its code/tests/contracts must be checked against the current tree. Other session plans need not be pre-read.

The [decision record](../docs/adr/0020-recovery-and-low-burden-workflow.md) explains the report assessment and scope exclusions. Session numbering 01–06 corresponds to the original S1–S6; scope and dependencies are unchanged.

- [01 — 远端操作恢复](../docs/plans/01-remote-recovery.md)
- [02 — Policy 与 Git 输入边界](../docs/plans/02-policy-and-git-inputs.md)
- [03 — Action、CI 与支持文档](../docs/plans/03-action-and-ci.md)
- [04 — 实现前 Packet 操作接口](../docs/plans/04-preimplementation-mutations.md)
- [05 — 验证、Ownership 与公开叙述](../docs/plans/05-evidence-and-narrative.md)
- [06 — Onboarding 与完整旅程](../docs/plans/06-onboarding-journey.md)

Each session uses implement-in-stages followed by delegated-change-review, and updates its own execution record plus the queue after accepted fixes are verified. All implementation sessions are **Not started**.
