# Separate Orientation from Assessment and invalidate stale understanding

Status: Superseded by ADR 0017 for semantic snapshots and profile-specific understanding requirements.

The understanding gate has two deliberate phases: Orientation explains the fixed contribution contract, final Diff, verification evidence, and policy result; Assessment then asks new questions that test the contributor's understanding without repeating the explanation. The Assessment is bound to a material snapshot and becomes invalid whenever those materials materially change, preventing an earlier answer from being treated as evidence for a different contribution.

## Considered Options

- Ask comprehension questions without a preceding structured explanation.
- Treat an Assessment as valid after it is answered, regardless of later changes.
- Pair Orientation with a snapshot-bound Assessment and regenerate it after material changes.

## Consequences

The contribution packet must identify the materials used for Orientation and Assessment. The CLI can invalidate stale records deterministically, while the Skill owns the explanatory and questioning interaction.
