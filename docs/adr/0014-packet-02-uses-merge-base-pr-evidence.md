# Packet 0.2 uses merge-base Pull Request evidence

Status: Superseded by ADR 0016 (private Packet/public Summary), ADR 0017 (Packet 0.3 clean break), and ADR 0019 (subject-digest evidence). This file is historical and is not a current compatibility contract.

Pull Request evidence uses the merge base of the selected base tip and head, matching the contribution view represented by GitHub's three-dot comparison. Packet `0.2` records `comparison=merge_base`, `base_tip_sha`, `merge_base_sha`, `head_sha`, the patch hash, changed files, and line counts. Remote operation identity binds the comparison mode, base tip, merge base, head, and patch hash. Remote readiness and Action enforcement additionally validate the complete record, including files and counts.

## Considered Options

- Keep Packet `0.1` and reinterpret its two-tip Diff fields as merge-base evidence.
- Compare the base tip directly with the head and accept unrelated base-branch changes in the contribution Diff.
- Introduce Packet `0.2`, reject older Packets at the new boundary, and share one merge-base capture implementation across CLI and Action paths.

## Consequences

The captured files and patch stay focused on the contribution when the base branch advances. A changed base tip, merge base, head, or patch invalidates prior confirmation, while a mismatch in any recorded Diff field blocks remote readiness and Action enforcement. Every Packet `0.1` file requires explicit regeneration because the runtime rejects the older Packet version globally. After regeneration, Issue and Signal operation identities and compatible receipts remain stable where their rendered remote operations did not change.
