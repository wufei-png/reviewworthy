# Changelog

## 0.3.0a1 - Unreleased

- Break all artifact and operation compatibility with earlier Reviewworthy formats.
- Keep the full Packet in ignored local state and publish a minimal versioned PR Body Evidence Summary.
- Replace patch-text identity with a canonical Git content `subject_digest`; the Action recomputes runner-owned facts and labels local verification and ownership as contributor claims.
- Replace Action `enforce` with the narrower `evidence-enforce` mode, which never reads a Packet from the checkout.
- Add Standard, Heightened, and Learning review profiles: Standard requires a light Ownership Check, while Heightened and Learning require full Orientation and Assessment.
- Bind contributor-local verification receipts to a versioned plan digest and canonical subject digest, and separate semantic freshness from timestamp and output-hash audit data.
- Replace Signal kind/status/publication flags with independent `record_type`, `claim_type`, `lifecycle`, `verification`, and `authority` axes; verify GitHub Discussions through GraphQL without adding Discussion publication.
- Make Action policy evaluation base-tree-only: structured TOML is the sole source of positive machine authority, document positives remain advisory, and explicit prohibitions, conflicts, or ambiguities can block `evidence-enforce`.
- Add derived `status`/`next` UX, version-isolated operation state, multiple-marker reconciliation stops, bounded subprocess capture, atomic artifact writes, and configurable risk path globs.

## 0.2.0a1 - Unreleased

- Introduce the breaking Packet `0.2` contract and bind remote Pull Request planning and Action enforcement to a recomputed merge-base Diff, current base tip, and current-head verification receipt; Packet `0.1` is rejected instead of reinterpreted.
- Bind Action enforcement to the runner repository slug and numeric repository ID, and reconcile created or discovered Pull Requests whose actual remote head is unavailable or differs from the approved operation.
- Parse bounded explicit policy negatives, block opposed claims in one source as `policy_ambiguity`, and enforce good-first-issue rules only from complete provider-verified Issue identity and labels with live pre-write revalidation.
- Add explicit human-confirmed candidate transitions from `issue_only` or `seek_maintainer_signal` to `plan_directly`, while preserving the underlying Issue/Signal gates and older bound-packet migration.
- Clarify that Reviewworthy governs external contributions; maintainer-authorized repository changes may use direct push, while repository-owned workflows decide when to invoke the read-only Action.
