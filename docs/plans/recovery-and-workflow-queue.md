# Reviewworthy recovery and workflow queue — 2026-09-30

Design status: **Approved by the user on 2026-09-30**. Sessions 01–06 are complete.

This is the approved implementation queue. Each session plan contains its own planned interfaces, target files, stages and acceptance criteria. Read this queue and only the selected session plan before inspecting its referenced code/tests/contracts.

## Purpose, baseline and independent execution

Improve recovery and complete the existing Skill-facing contribution journey without adding unnecessary Agent data structures. The authoritative decisions are [ADR 0020](../adr/0020-recovery-and-low-burden-workflow.md). The fixed decisions needed for execution are summarized below; consult the ADR if a boundary needs clarification. The external report and other session plans need not be pre-read.

Repository: `/Users/wufei2/github.com/wufei-png/reviewworthy`.
Baseline: `61b83d3449aaeb566eb4e0a9865b19022ce9855d`.
Source assessment: `/Users/wufei2/github.com/wufei-png/project-portfolio-review-2026/reports/19-reviewworthy.md`. Reading that external report is optional; its selected requirements and rejected proposals are recorded here and in ADR 0020.

At planning time, the tree was clean before these documents were written. Python 3.11.5 passed 238 unit tests and 11 eval fixtures. Inspect the current target files and applicable tests in each implementation session; do not assume later HEAD still equals the baseline.

Read `AGENTS.md`, `CONTRIBUTING.md`, the named target modules/tests, and the relevant active references. Use `/Users/wufei2/.agents/skills/implement-in-stages/SKILL.md`: at most ten independently valid stages per session, one scoped local commit per verified stage. Implementation takes place in the current tree. Do not stage unrelated existing changes, push, publish a release, create remote objects, or run a mutation canary under this plan.

This is a maintainer-authorized local implementation task when the user invokes the selected session prompt. It does not require manufacturing an external contribution Issue or PR. The application's normal external-contribution gates remain intact.

## Scope filter and fixed decisions

- Exclude proposals conflicting with existing contracts or the user's requirements unless explicitly authorized. Include necessary compatible work regardless of its original priority.
- Explicitly authorized adjustments: policy source option A and manual-inspection/explicit-retry option B.
- Private Packet, minimal public Summary, Skill-first conversation, read-only Action, explicit remote operation confirmation, public GitHub identity and human-owned authority remain constraints.
- Existing artifact versions and schemas remain the starting contract. No speculative migrations, required capabilities, extension envelopes, private basis type, Discussion publication, authority inference, second provider, synchronization service or global exactly-once promise.
- Reuse existing section payloads. Derived hashes, snapshots, node results and invalidation belong to the CLI. A new flag or command may expose a needed action; it must not require a duplicate declaration of the same business fact.
- Shared operation logic, contract fixtures, bounded duplicate checks and simple actionable diagnostics are included. Do not exclude them merely because the report ranked them below other work.
- Command spellings in the selected session plan are the planned interface. A small naming adjustment is permitted if actual parser evidence warrants it; document the final spelling and preserve the stated semantics. Changing a settled product decision requires grilling, not unilateral expansion.

## Session order and dependency graph (ordering reference)

| Session | Result | Earlier foundations | Reason for execution order |
|---|---|---|---|
| 01 | Recover existing remote operations and explicitly retry uncertainty | None | Unblocks a currently stranded user and preserves old operations before other changes. |
| 02 | Narrow/bound policy inputs and fix Git path determinism | None | Policy and Diff feed all subsequent interfaces. |
| 03 | Action/CI prerequisite and documentation closure | 02 | New policy failures must reach Action enforcement; other hygiene could run independently. |
| 04 | Typed pre-implementation Packet mutations | 02 | Builds on finalized policy/path behavior. |
| 05 | Typed post-implementation mutations and evidence invalidation | 04 | Needs the shared mutation and result-maintenance rules. |
| 06 | Start/next orchestration and complete hermetic journey | 01–05 | Integrates proven primitives rather than creating a second workflow. |

Run 01 → 02 → 03 → 04 → 05 → 06. No separate dependency-completion audit is required. Do not run separate editing sessions concurrently in this shared tree. Priority places 01/02 first; dependencies place onboarding last. 03 is included even though it is cheaper and was ranked lower in the report.

## Shared checks and completion rules

Focused checks (use the package imports with `PYTHONPATH=src:tests`):

```bash
PYTHONPATH=src:tests python -m unittest tests.test_github tests.test_cli -v
PYTHONPATH=src:tests python -m unittest tests.test_policy tests.test_git tests.test_action tests.test_schema -v
PYTHONPATH=src:tests python -m unittest tests.test_packet tests.test_workflow tests.test_cli tests.test_schema -v
PYTHONPATH=src:tests python -m unittest tests.test_docs tests.test_artifacts -v
```

At the end of each code session:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m reviewworthy eval run --json
python -m compileall -q src tests
git diff --check
```

For schema changes, run `PYTHONPATH=src:tests python -m unittest tests.test_schema -v` with the test-only dependency from `requirements-dev.txt`. Runtime remains standard-library-only. For 03/06, also run `PYTHONPATH=src python -m reviewworthy action check --mode report`; absence of a PR event is a local smoke test, not event enforcement evidence. Use fixture-owned event/Git objects for actual enforcement tests.

06 also builds a wheel with `python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/reviewworthy-wheel .`, then installs and runs it in a clean temporary environment. Check `setuptools>=68` is available first. Do not call a skipped build, unavailable interpreter, local fake provider, or fixture run a live-provider success.

For every stage: test the behavior, stage explicit paths, inspect the staged diff, run `git diff --cached --check`, then commit. Include relevant active docs/changelog with the stage that delivers the behavior. Keep meaningful failure/invalidation coverage beside the affected module; do not add snapshots of every field or combinatorial matrices without a concrete contract.

After implementation, run delegated-change-review once with a fresh read-only subagent. Adjudicate every finding; fix accepted findings separately and rerun relevant checks. Record rejected findings with reasons. Review the full selected-session diff from its comparison base, not merely the last commit. Accepted fixes require their own rechecks; a review timeout is not approval. Update the selected plan and this queue with commits, checks, review decisions, fixes, final interfaces and unverified items. `Complete` requires the session acceptance criteria, applicable checks and review adjudication; otherwise record partial work or blockers honestly.

## Session plans and execution record

The plan numbers 01–06 correspond to the approved design's original S1–S6. Numbering changed for the session prompts; scope and hard dependencies did not change.

| Session plan | Status | Commits | Checks/review/fixes | Deviations/unverified items |
|---|---|---|---|---|
| [01 — 远端操作恢复](./01-remote-recovery.md) | Complete (2026-09-30) | `bff7626`, `5ba38e9`, `f71e7e6`, `db001c2`, `9b05957`; fixes `be4767d`, `43cc333` | 262 unit tests, 11 evals, compileall and full-range diff checks passed. One fresh read-only review; both P2 findings reproduced, accepted and fixed; focused rechecks passed. | Final interfaces match the plan. No live GitHub writes or push. Pre-existing current Signal snapshot/whitespace omissions and bounded visibility/race limits are documented in 01. |
| [02 — Policy 与 Git 输入边界](./02-policy-and-git-inputs.md) | Complete (2026-09-30) | `b575ac8`, `93825f9`, `f9ff4cc`; audit fix `322289a`; review fix `11e1b3d` | 292 unit tests, 11 evals, compileall and full-range diff checks passed. One fresh read-only review found one P2 Gitlink parity defect; independently reproduced, accepted and fixed; 108 focused tests and final regression/full rechecks passed. | Existing CLI unchanged; exact optional authoritative-document list and bounded policy diagnostics delivered. Unusual historical Diff fields may need rebinding/reverification; saved-operation recovery remains intact. Python 3.12/3.13 and live-provider checks unverified locally; no remote writes/push. |
| [03 — Action、CI 与支持文档](./03-action-and-ci.md) | Complete (2026-09-30) | `afe6fbb`, `d8c9741`; final documentation commit closes the record | 298 unit tests, 11 evals, compileall and full-range diff checks passed. One fresh read-only review: No findings; reviewer independently passed 33 Action tests and verified upstream pins. Documentation/artifact checks rerun for record closure. | Wrapper preflight exits 2 before imports; CLI/contracts unchanged. Upstream pins verified live; fixture enforcement is provider-free. Python 3.12/3.13, actual old Python, live GitHub runner/provider and wheel/release checks unverified locally; no remote writes/push. |
| [04 — 实现前 Packet 操作接口](./04-preimplementation-mutations.md) | Complete (2026-09-30) | `df7c515`, `1556bce`, `0d4442d`, `d28abf4`; review fixes `d7c36f3`, `c4fa93a`; audit fix `a5a6745`; final documentation commit closes the record | 315 unit tests, 11 evals, compileall and full-range diff checks passed. One fresh read-only review independently passed 124 focused tests; two P2 findings reproduced, accepted and fixed separately; 82 and 72 focused rechecks; final idempotence audit fix passed 83 focused tests; final regression passed. | Six planned domain operations delivered; optional basis `--repository` supplies local-Signal identity without a new envelope. Candidate/provider gates retained; identical semantic updates preserve evidence and material updates reset affected approval/results. Python 3.12/3.13, live provider/runner and wheel/release unverified locally; no remote writes/push; 05/06 not started. |
| [05 — 验证、Ownership 与公开叙述](./05-evidence-and-narrative.md) | Complete (2026-09-30) | `1987d6c`, `84e2af0`, `32d0282`; review fixes `a56c2f2`, `c70505c`; final documentation commit closes the record | 327 unit tests, 11 evals, compileall and full-range diff checks passed. One fresh read-only review independently passed 56 focused checks; both P2 findings reproduced, accepted and fixed separately; 53 and 79 focused rechecks passed; final regression and documentation/artifact checks passed. | Typed Ownership/AI and narrative record/preview/confirm delivered; exact remote prose matching, current-receipt results and material invalidation covered by Standard and Heightened/Learning CLI journeys. Existing schemas/artifact versions retained; historical understanding snapshots may need current re-recording. Python 3.12/3.13, live provider/runner and wheel/release unverified locally; no remote writes/push; 06 not started. |
| [06 — Onboarding 与完整旅程](./06-onboarding-journey.md) | Complete (2026-09-30) | `afe0dab`, `72457ea`, `96bc23e`; review fixes `77a62a4`, `3f3d077`; final documentation commit closes the record | 338 unit tests, 11 evals, compileall, schema/artifact and full-range diff checks passed. One fresh read-only review completed after a usage-limit interruption; both P2 findings independently reproduced, accepted and fixed separately; 24/25 focused rechecks passed. Local Action report smoke passed without a PR event. Rebuilt wheel with setuptools 84.0.0; clean no-deps install, seven onboarding and four E2E methods passed outside the checkout. All 27 documentation/artifact closure tests passed. | Start and ready-boundary next/recovery delivered without new schemas/session state. Repeated start retains approved decisions/prose and reports missing focus; both plain Issue and Issue Signal evidence reuse covered. Tooling shapes do not prove npm/Go execution; Python 3.12/3.13, live provider/runner and a published release unverified; no remote writes/push. |

Implementation evidence may revise only unfinished stages within the approved contracts. A necessary change conflicting with a fixed constraint requires a concrete grilling decision; do not implement it by rewriting the constraint. Necessary compatible work cannot be discarded only because it is lower priority.
