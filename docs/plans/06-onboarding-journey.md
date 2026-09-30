# 06 — Onboarding 与完整旅程

Design status: **Approved (2026-09-30)**. Execution status: **Implemented; delegated review pending**.

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

- Status: Implemented; delegated review pending (2026-09-30).
- Comparison base: `894e1f9a6c55627018bd5c06c40efa9c30270ea2`.
- Commits: `afe0dab` (retryable start; 82 focused tests), `72457ea` (next/recovery and journeys; 59 focused tests); current documentation stage records distribution evidence.
- Checks/results: Python 3.11.5 passed 336 unit tests (including schema/generated-artifact validation), 11 eval fixtures, compileall and diff checks. Local Action report smoke passed with `checked=false` because no PR event was supplied; event enforcement is covered by hermetic Git/event fixtures. Build environment used setuptools 84.0.0 and `pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/reviewworthy-wheel .`. A separate clean environment installed that wheel with `--no-deps`, reported version `0.3.0a1`, and ran all four E2E test methods from `/tmp` without source PYTHONPATH. Import resolved to that environment's site-packages; wheel metadata has no runtime dependencies.
- Review findings and decisions: Pending one fresh read-only review over the full comparison-base diff.
- Fixes and rechecks: None yet.
- Final interfaces: `start --root ROOT --contribution-id ID --issue URL [--focus PATH ...] --json`; existing `status/next --packet FILE --json` retained. Start returns Git-private Packet/Brief paths, freshness findings, verification provenance and derived status; existing decisions/prose are preserved, recorded Issue verification is reused explicitly, and deliberate changes use existing typed operations. Ready `next` returns a decision hint for actual refs/Body export, or an executable `remote reconcile --state FILE --json` for an exact current unresolved PR operation. No new schema/artifact version or session state.
- Evidence boundaries: Python, Node and Go tooling-shape journeys use real Git and Python subprocess receipts with a strict fake gh transport. npm/Go execution, Python 3.12/3.13, live GitHub/provider/runner permissions and a published release remain unverified locally. No push or remote object creation was performed.
