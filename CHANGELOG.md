# Changelog

## 0.2.0a1 - Unreleased

- Introduce the breaking Packet `0.2` contract and bind remote Pull Request planning and Action enforcement to a recomputed merge-base Diff, current base tip, and current-head verification receipt; Packet `0.1` is rejected instead of reinterpreted.
- Bind Action enforcement to the runner repository slug and numeric repository ID, and reconcile created or discovered Pull Requests whose actual remote head is unavailable or differs from the approved operation.
- Parse bounded explicit policy negatives, block opposed claims in one source as `policy_ambiguity`, and enforce good-first-issue rules only from complete provider-verified Issue identity and labels with live pre-write revalidation.
- Add explicit human-confirmed candidate transitions from `issue_only` or `seek_maintainer_signal` to `plan_directly`, while preserving the underlying Issue/Signal gates and older bound-packet migration.
- Clarify that Reviewworthy governs external contributions; maintainer-authorized repository changes may use direct push, while repository-owned workflows decide when to invoke the read-only Action.
