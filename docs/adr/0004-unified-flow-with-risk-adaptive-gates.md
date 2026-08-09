# Converge contribution entries into one risk-adaptive flow

Status: Superseded by ADR 0017 for review profiles and understanding requirements.

Issue-backed and Discovery are entry paths, not separate implementation workflows. After a contribution basis is recorded, both enter the same contribution-contract, implementation, verification, understanding, and PR sequence; every stage records a result, while the depth of checks is either `standard` or `heightened`. Risk signals and user escalation may raise the depth, but security issues, policy conflicts, irreversible changes, and unverifiable results are independent hard-stops. Understanding always runs as Orientation followed by a non-duplicative Assessment, and an Assessment expires when its source materials materially change. This avoids duplicated lifecycle logic without allowing low-risk work to silently omit accountability evidence.

## Considered Options

- Maintain separate Issue-backed and Discovery lifecycles.
- Use one shared lifecycle with fixed-depth gates for every change.
- Use one shared lifecycle with two review depths, independent hard-stops, and mandatory result records.

## Consequences

The domain model needs explicit entry, contribution-basis, material-snapshot, result, and assessment records rather than separate state machines. Risk signals become auditable inputs to review depth, not model-confidence shortcuts.
