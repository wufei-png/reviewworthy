# ADR 0017: Review profiles and semantic verification

## Decision

Packet `0.3` has three explicit review profiles. `standard` requires a concise contributor Ownership Check covering the problem, bounded scope, verification, and risks. `heightened` and `learning` require that check plus the full Orientation and Assessment records. Risk signals raise a Standard contribution to Heightened; Learning is an explicit educational posture rather than a lower assurance level.

Verification is plan-driven. Each check has a stable ID, argv, repository-relative cwd, and required flag. A contributor-local receipt is current only when it uses receipt `0.3`, matches the exact plan digest and contribution `subject_digest`, records a stable Git/worktree boundary, and passes the command.

Freshness uses a semantic snapshot. It includes contribution decisions, canonical diff identity, the verification plan, semantic receipt outcomes, policy conclusions, review profile, and Ownership Check. Timestamps, stdout/stderr hashes, and other audit-only data do not invalidate understanding.

## Consequences

- Standard contributions avoid mandatory grilling while retaining explicit contributor accountability.
- Heightened and Learning contributions retain the full understanding gate.
- Editing a verification plan or contribution subject invalidates its receipts.
- Re-recording equivalent audit timestamps or output hashes does not invalidate understanding.
- Pre-0.3 verification fields and receipts are rejected; they are not recognized or migrated.
