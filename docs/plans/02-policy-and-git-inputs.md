# 02 — Policy 与 Git 输入边界

Design status: **Approved (2026-09-30)**. Execution status: **Not started**.

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

- Status: Not started.
- Comparison base and commits: —
- Checks/results: —
- Review findings and decisions: —
- Fixes and rechecks: —
- Final interfaces/deviations/unverified items: —
