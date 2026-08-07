# Changelog

## 0.1.4 - Unreleased

- Bind remote Pull Request planning and Action enforcement to a recomputed complete Diff and current-head verification receipt.
- Normalize repository identity, Issue state reasons, duplicate labels, and policy provenance at their actual evidence boundaries.
- Add explicit human-confirmed candidate transitions from `issue_only` or `seek_maintainer_signal` to `plan_directly`, while preserving the underlying Issue/Signal gates and older bound-packet migration.
- Keep the Action read-only and report/enforce semantics explicit, with no implicit fetch or maintainer-response inference.
