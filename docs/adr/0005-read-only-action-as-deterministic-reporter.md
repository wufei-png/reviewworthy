# Keep the GitHub Action read-only and deterministic

The GitHub Action reports only objectively checkable policy or evidence violations and never comments, closes, or edits a Pull Request. Unknown policy or evidence is reported as an unresolved finding but does not fail the Action by default; mutation decisions remain in the explicitly confirmed CLI/Skill flow, where the full contribution context is available.

## Considered Options

- Make the Action an advisory-only reporter for all findings.
- Let the Action fail deterministic violations while reporting unknowns without blocking.
- Let the Action use an LLM to decide and enforce contribution quality.

## Consequences

The Action must separate deterministic failure from informational uncertainty and must not claim that a successful run proves the contribution is reviewworthy.
