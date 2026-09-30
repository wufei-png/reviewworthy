# 02 — Policy 与 Git 输入边界

Design status: **Approved (2026-09-30)**. Execution status: **Complete (2026-09-30)**.

Earlier foundations (ordering reference): 无硬依赖；按批准顺序在 01 后执行。

Follow the [shared queue](./recovery-and-workflow-queue.md), execute only 02. Other session plans need not be pre-read. Commands introduced here are planned interfaces, not baseline capabilities.

Read: `policy.py` discovery/tree extraction/structured claims, `git.py` Diff and canonical path functions, `action.py` policy projection/blockers, `brief.py` source manifests, relevant schemas/references, and their tests.

## Contract

- Defaults: root `README.md`, `README`, `CONTRIBUTING.md`, `CONTRIBUTING`, `AGENTS.md`, `SECURITY.md`; `.github` Issue/PR template files/directories (case conventions supported by GitHub templates). Do not automatically scan arbitrary `.github` files or `docs`. Keep project orientation discovery separate.
- Optional TOML `[discovery] authoritative_documents = ["docs/contributing.md"]` adds exact paths to defaults. Validate canonical repository-relative paths, existence, regular-file/text readability and types. No directory/glob expansion or implicit override. A missing explicit source is a blocker, not silence.
- Use the same source-selection and claim rules for local files and immutable commit trees. NUL-delimited tree entries must retain mode information so symlinks are not accidentally treated as regular text blobs. Local scans do not follow policy-source symlinks; report the same unsupported-source condition for matching tree modes.
- Start with constants: at most 128 selected sources, 1 MiB per source, and 8 MiB total, including structured policy. Check counts/sizes before content parsing; fixed budgets do not become required user configuration. Bound Git calls with existing subprocess limits. Whole-tree enumeration may hit its existing output/time limit; return a stable unavailable/limit diagnostic instead of a traceback.
- Unknown TOML keys and invalid supported values receive explicit path-bearing diagnostics. Normalize existing accepted aliases before validating canonical fields; test their intended behavior instead of accidentally rejecting them. Keep the schema aligned for canonical policy and the optional discovery table. No mandatory `policy_version`.
- Read/decode/path/limit failures cannot result in usable positive policy permission. Contributor readiness and Action `evidence-enforce` must receive blockers; `report` remains reporting. Wire new hard stops through the Action projection, rather than only adding them to policy output.
- Preserve conflict/ambiguity behavior and positive base-tree structured-policy authority. Documents listed by the PR head do not control the base-tree Action scan.
- `git diff --name-only` and `--numstat` use NUL records; decode supported paths consistently and retain no-renames behavior. Preserve `git-raw-content-v1`, ordinary-file results and raw digest. Invalid encodings or paths outside the existing canonical contract fail explicitly; do not add public hex-path fields.
- Use existing diagnostic structures with stable ordering. Do not introduce severity/expected/actual envelopes or expose full policy text in default Action diagnostics.

## Stages

1. Narrow default discovery and explicit list, including TOML runtime/schema validation — check policy/schema/Brief compatibility.
2. Bounded source reading and Git-tree parity with Action blocker propagation — check policy/Action tests and malformed-source cases.
3. NUL Diff paths/statistics — check Git/Packet/Action tests, scope enforcement and changed-file contract notes.

## Acceptance

Tests cover irrelevant conflicting release/tutorial text being ignored; explicit docs becoming sources; contradictory authoritative sources blocking; unknown keys/types; missing files; non-UTF8 text; symlinks; count/per-file/total limits; and local-vs-same-commit claims/diagnostics parity. Compare normalized provenance/claims, excluding the expected repository/base location metadata.

For Git, use real temp repos with Unicode, tab/newline names, supported punctuation, binary files, additions/deletions and no-renames transitions. Toggle `core.quotePath`; compare scope paths, counts and semantic identity. Unsupported byte names receive controlled errors. Do not expand into a full Cartesian environment matrix; retain the existing Python CI matrix and add focused order/hash-seed comparisons only where needed.

Document that unusual-path historical Diff fields may require rebinding/reverification. 01 must still recover their original saved operation without re-rendering it.

## Review and execution record

Use implement-in-stages for scoped local commits, then delegated-change-review for one fresh read-only review of this session's full change. Record the comparison base, findings, accepted/rejected decisions, verified fixes and unverified items. Complete the relevant rechecks after each accepted fix before marking this session complete.

Update this plan and the queue together after implementation/review; do not start the next session automatically.

- Status: Complete (2026-09-30).
- Comparison base: `88be02ac2e49ccea43ec784b8cc83f10dd95ac58`. The fresh review covered the full selected-session change through `322289a`; accepted-finding fix `11e1b3d` was independently verified afterward.
- Stage commits: `b575ac8` narrows default sources and validates optional discovery/canonical policy plus accepted aliases; `93825f9` bounds reads, shares local/tree rules and propagates blockers through Action, Packet and workflow; `f9ff4cc` uses NUL Diff names/numstat, exact scope paths and unchanged raw identity. Each stage passed focused checks, explicit staged-diff inspection and whitespace checks before its local commit.
- Final audit fix: `322289a` converts reproduced TOML depth and integer-conversion limits into path-bearing configuration diagnostics. Policy/Action focused rechecks passed (68 tests).
- Checks/results: Python 3.11.5 full `PYTHONPATH=src python -m unittest discover -s tests -v` passed 292 tests after the accepted review fix; `PYTHONPATH=src python -m reviewworthy eval run --json` passed all 11 fixtures; `python -m compileall -q src tests`, `git diff --check` and full-session `git diff --check 88be02a..HEAD` passed. Focused Policy/Schema/Brief/Action and Git/Packet/Action/recovery checks passed; documentation closure checks (`tests.test_docs tests.test_artifacts`) passed 27 tests. Real temp repositories covered unusual paths, additions/deletions, binary files and disabled renames; `core.quotePath` toggles and two hash seeds preserved scope paths, counts and semantic identity. Local/tree tests compare all claims, provenance and diagnostics after excluding base location metadata.
- Review findings and decisions: one fresh read-only `$review-agent` using delegated-change-review returned one P2: an initialized Gitlink ancestor could supply positive local policy while the same commit tree rejected it. Independently reproduced with `docs/policy.md` in a real submodule; accepted. No rejected findings and no other qualifying findings. The reviewer ran 123 focused tests successfully.
- Fixes and rechecks: `11e1b3d` reads bounded local index modes, rejects Gitlink ancestors and avoids scanning submodule template contents. Real initialized-submodule regression cases cover explicit docs, a default template container and a nested template submodule; unavailable Git metadata blocks positive authority while plain-directory policy inspection remains usable without a Git executable. The relevant Policy/Action/Brief/workflow suite passed 108 tests, final focused regression rechecks passed 3 tests, then the full 292-test suite and 11 evals passed.
- Final interfaces/deviations: existing CLI spellings are unchanged. Optional `[discovery] authoritative_documents` selects exact additional paths; wildcard punctuation is literal and never expanded. Canonical schema/runtime checks retain supported Unicode and tab/newline path boundaries. Fixed budgets are 128 sources, 1 MiB/source and 8 MiB total, including structured policy; the bounded TOML bootstrap discovers the list before document count/size preflight. Ordered `policy_*` input diagnostics become contributor hard stops and `base_policy_*` Action enforcement violations; report remains non-blocking. Brief keeps orientation separate and preserves blockers without hashing failed policy sources. No new required version field or public hex-path field.
- Historical evidence: active contract notes explain that unusual-path historical Diff fields may require rebinding and reverification for a new plan; a regression proves 01 still reconciles the original retained operation ID without re-capturing the Diff or rendering another operation.
- Unverified items/remaining limits: Python 3.12/3.13 CI jobs were not run locally; their existing matrix is unchanged. Tests are hermetic/local and do not prove live-provider behavior. No live GitHub writes, remote objects, mutation canary or push. Whole-tree/index enumeration can still reach its bounded Git output/time limits and then fails with controlled unavailability. Local policy inspection observes current filesystem/index inputs rather than promising an atomic repository snapshot. Session 03 was not started.
