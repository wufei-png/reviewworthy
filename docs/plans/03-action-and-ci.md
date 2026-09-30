# 03 — Action、CI 与支持文档

Design status: **Approved (2026-09-30)**. Execution status: **Complete (2026-09-30)**.

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

- Status: Complete (2026-09-30), scoped local implementation only.
- Comparison base: `a4c316b06c1362872ac9e28ad0f684676cde014f`.
- Stage 1: `afe6fbb` — composite Python/Git preflight, immutable upstream CI pins,
  checkout credentials disabled, and fixture enforcement/diagnostic coverage.
  33 Action tests and 102 CLI/Policy/Git/Schema tests passed; after moving the
  poisoned Packet fixture to current Git-private state, its wrapper integration
  test passed again. Compileall and staged diff checks passed before commit.
- Stage 2: `d8c9741` — Action permissions/history/trust/pinning guidance,
  public-provider and private security-intake boundaries, durable eval description,
  and release guidance with the explicit uncertain-create retry exception.
  27 documentation/artifact tests passed. Newly executed evidence is recorded here,
  separately from the existing release checklist.
- Final checks: `PYTHONPATH=src python -m unittest discover -s tests -v` passed
  **298 tests** on Python **3.11.5**; `PYTHONPATH=src python -m reviewworthy eval run --json`
  passed **11 fixtures**; `python -m compileall -q src tests`, worktree/staged/full-range
  diff checks passed. `action check --mode report` without a PR event passed with
  missing-Summary unknowns: this is runtime smoke evidence only. Repository policy
  dogfood inspection remained explicit with no conflicts, ambiguities or diagnostics.
- Enforcement evidence: actual composite Bash execution over fixture-owned
  PR events/Git objects passed and rejected unavailable base objects; malformed
  JSON/event shapes remained non-blocking in report and failed enforcement.
  Base-policy tests cover invalid configuration, invalid encoding, byte limits,
  unsupported symlinks and controlled unreadable-blob failures, alongside the
  existing missing-source, conflict, ambiguity and base-authority tests. Recorded
  Git calls were read-only; the poisoned current private Packet was untouched,
  and the `gh` trap was never invoked. Old Python is simulated by a test shim;
  missing/broken Python and Git are exercised with a controlled PATH.
- Upstream evidence: official `git ls-remote` and release/commit pages were checked
  on 2026-09-30. `actions/checkout` `v7`/`v7.0.1` resolved to
  `3d3c42e5aac5ba805825da76410c181273ba90b1`; `actions/setup-python` `v7`/`v7.0.0`
  resolved to `5fda3b95a4ea91299a34e894583c3862153e4b97`. Source links are in
  [the active Action reference](../../references/action-and-ci.md).
- Review: one fresh read-only subagent using `review-agent`, via
  `delegated-change-review`, inspected the full `a4c316b..d8c9741` change and
  relevant call sites. Conclusion: **No findings**. Accepted/rejected findings:
  none; no review fixes required. The reviewer independently passed all 33 Action
  tests and full-range diff checks and confirmed the official upstream pins.
- Record closure: this plan and the queue are updated together in the final
  documentation commit; documentation/artifact and full-range diff checks are
  rerun for that record update.
- Final interfaces: no new CLI command, flag, schema or artifact version. The
  composite wrapper exits **2** for unusable prerequisites in either mode before
  imports; usable-runtime `report` findings remain non-blocking. Existing
  `evidence-enforce` behavior and the Python 3.11–3.13 CI matrix are preserved.
- Deviations/unverified items: none in scope. Python 3.12/3.13 and an actual old
  Python interpreter, live GitHub runner/provider behavior, wheel installation and
  release validation were not executed locally. No push, publication, remote
  writes or mutation canary. Full history, trusted pinned execution and bounded
  remote visibility/race limits remain documented operational constraints.
