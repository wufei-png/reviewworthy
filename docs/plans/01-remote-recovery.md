# 01 — 远端操作恢复

Design status: **Approved (2026-09-30)**. Execution status: **Not started**.

Earlier foundations (ordering reference): 无。

Follow the [shared queue](./recovery-and-workflow-queue.md), execute only 01. Other session plans need not be pre-read. Commands introduced here are planned interfaces, not baseline capabilities.

Read: `github.py` (`RemoteOperation`, `build_operation`, `build_signal_operation`, `operation_lock`, state readers/writers, `GhClient.find_existing`), `cli.py` (`_remote_operation`, `_remote_pr_head_reconciliation`, `_link_pull_request`, both create handlers), `tests/test_github.py`, `tests/test_cli.py`, `references/remote-writes.md`, ADRs 0007/0019, and `THREAT_MODEL.md`.

## Contract

1. Add `remote reconcile --state FILE --json`, plus optional `--confirm-operation-id ID`. `FILE` is an existing current operation record. Reconstruct and validate its stored operation; do not require current Packet readiness, current Git refs, or title/body resubmission for inspection/local repair. Do not read older state formats or automatically discover legacy paths.
2. Separate parsing/validation from create's existing rule that pending means stop. Validate version, shapes/types, ID/marker consistency, repository ID/slug, kind, purpose, URLs, and local status. Original marked bodies may have lost trailing whitespace during creation, so do not pretend the record can always reproduce the original ID hash from its marked body alone. It is local implementation state, not signed authority.
3. Verify immutable live repository identity. Read a known canonical URL directly and inspect its marker/kind; also perform bounded marker search to detect ambiguity. Unknown URL: zero matches preserves pending; one match repairs state; multiple matches return all canonical URLs and block. Missing markers or live payload/head drift are actionable findings, not permission to create another object or repair a public body automatically.
4. For PRs, inspect the original operation head and the exact Issue URL note. Without confirmation, record the existing evidence and report the missing link action. With the matching original operation ID, the one absent note may be written after commentability and head rechecks. Reuse the existing one-line note contract, make at most one note attempt, and never create a PR on this path. A note already present is not posted again.
5. Add `signal publish reconcile SIGNAL_PATH --state FILE --json` using the same recovery logic. Backfill the original publication's reference/subject/publication fields only into the matching Signal/target artifact. Check subject identity and reject unrelated or materially edited targets. Do not infer confirmed lifecycle or maintainer authority.
6. Add `--retry-uncertain` to the existing `remote create` and `signal publish create`. It requires valid pending object-creation state, the matching confirmed operation, normal readiness/current-input validation, verified repository identity, and a fresh zero-match search. If one match appears, reconcile it; if multiple appear, stop. Keep write-ahead state and make one create attempt. Reject use on linked/created PRs, note failures, invalid records, or absence of a pending operation. Communicate that manual inspection and opt-in retry accept residual duplicate risk.
7. After create, read/verify the known object and perform one bounded post-create marker search. Report visible duplicates with URLs. A zero-match list or unavailable list does not erase a successful canonical response; retain the known URL and distinguish incomplete live inspection from a verified result. Persist enough existing state to recover after another local-write failure. No repeated polling or global coordination.
8. Preserve the current operation ID algorithm, marker spelling, state version/path and successful immediate-retry behavior. Cached `already_exists` with `source=local_receipt` is historical; reconcile is the current remote check. Keep output additions small, using existing outcomes and code/message/path diagnostics where applicable.

## Stages (at most six)

1. Validated current-state loading and shared operation seam — preserves create's default refusal, adds operation contract fixtures; check remote-focused tests.
2. Issue/PR reconciliation CLI — remote-read/local-repair cases, known URL drift and confirmation-controlled backlinks; check remote-focused tests.
3. Signal reconciliation — recovers publication plus artifact-write interruption without overwriting unrelated work; check remote-focused tests.
4. Explicit uncertain retry — one attempt with the same operation, no retry of partial PR/link state; check fault tests.
5. Bounded post-create duplicate inspection and recovery guidance — preserves known results through failures, reports all duplicates; check fault tests and docs.

Each stage includes its own relevant tests/docs; do not postpone all tests into stage five. Extract only the logic actually shared by these paths, for example into `remote.py`, while keeping `GhClient` as transport. A large provider interface or directory restructuring is outside scope.

## Acceptance

- Create accepted remotely + local receipt failure → reconcile repairs state without another create.
- Current Packet, body input file or branch may change after the saved operation; read/local repair of that operation still works.
- Zero/one/multiple marker cases, remote head/marker drift, malformed/unreadable state, existing/missing/uncertain Issue note, and Signal update failure are covered.
- No confirmation means no remote mutation. Wrong ID, incomplete inspection, multiple matches, or invalid state cannot bypass the checks.
- A pending zero-match operation retries only with the explicit switch and matching ID; another failure remains recoverable.
- Duplicate races are covered with an injected provider sequence. Detection covers visible records, not a promise that every concurrent write is instantly visible.
- Killing a process may leave a lock: ordinary commands fail closed and provide concrete manual recovery guidance. No automatic age-based lock deletion.

## Review and execution record

Use implement-in-stages for scoped local commits, then delegated-change-review for one fresh read-only review of this session's full change. Record the comparison base, findings, accepted/rejected decisions, verified fixes and unverified items. Complete the relevant rechecks after each accepted fix before marking this session complete.

Update this plan and the queue together after implementation/review; do not start the next session automatically.

- Status: Not started.
- Comparison base and commits: —
- Checks/results: —
- Review findings and decisions: —
- Fixes and rechecks: —
- Final interfaces/deviations/unverified items: —
