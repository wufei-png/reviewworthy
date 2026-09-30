# 03 — Action、CI 与支持文档

Design status: **Approved (2026-09-30)**. Execution status: **Not started**.

Earlier foundations (ordering reference): 02。

Follow the [shared queue](./recovery-and-workflow-queue.md), execute only 03. Other session plans need not be pre-read. Commands introduced here are planned interfaces, not baseline capabilities.

Read: `action.yml`, `.github/workflows/reviewworthy.yml`, `references/action-and-ci.md`, `docs/release/0.3.0a1.md`, `SECURITY.md`, `evals/README.md`, `tests/test_docs.py`, Action wrapper and artifact tests.

## Stages and acceptance

1. Preflight and immutable CI dependencies — check Python >=3.11 and Git availability before imports/operations that would otherwise fail opaquely. Use clear prerequisite errors; document that non-blocking report findings are different from an unusable runtime. Resolve the currently configured upstream Action tags to verified full commits using official upstream evidence at implementation time; do not copy guessed or stale SHAs. Add `persist-credentials: false`. Composite Action stays Python/Bash plus this package, without new third-party `uses:`.
2. Delivery/reference closure — document minimal permissions, complete Git history, base-tree authority, immutable consumer pins and the hazards of executing untrusted head code with privileged events. Correct the eval-count statement; prefer durable wording or an existing-fixture count check rather than a generation framework. Clarify public-provider support and private security intake without adding private provider APIs/basis formats or changing the private-reporting exception.

Use fixture events for invalid JSON/shapes, unavailable base objects, unreadable base policy and new policy blockers. Preserve tests that the Action does not read a Packet, invoke `gh`, fetch or write comments. Keep the current Python 3.11–3.13 CI validation claim, with runtime >=3.11 and no third-party runtime dependencies.

Describe 01's explicit retry exception accurately; do not promise global exactly-once. Do not rewrite historical release evidence as new evidence, invent a release tag, use an unpublished local SHA as a usable consumer pin, or run a live mutation canary. Record newly executed checks separately.

## Review and execution record

Use implement-in-stages for scoped local commits, then delegated-change-review for one fresh read-only review of this session's full change. Record the comparison base, findings, accepted/rejected decisions, verified fixes and unverified items. Complete the relevant rechecks after each accepted fix before marking this session complete.

Update this plan and the queue together after implementation/review; do not start the next session automatically.

- Status: Not started.
- Comparison base and commits: —
- Checks/results: —
- Review findings and decisions: —
- Fixes and rechecks: —
- Final interfaces/deviations/unverified items: —
