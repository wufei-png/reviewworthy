# Make the Skill, CLI, and GitHub integration first-class parts of the MVP

The first release includes a portable Agent Skill, a Python standard-library CLI, and GitHub integration capable of creating Issues and Pull Requests. Remote writes are a deliberate product capability, but every write must remain policy-aware and explicitly attributable to the user's approved contribution flow so that automation does not outrun human ownership. After the contribution passes its substantive gates, the default is to create the requested formal Pull Request directly; Draft is used only when the repository policy or a meaningful early-maintainer-review step requires it.

## Considered Options

- Ship only a prompt-based Skill and defer deterministic tooling.
- Ship local-only artifacts and never write to GitHub.
- Ship the Skill, deterministic CLI, and GitHub write path together.

## Consequences

The MVP must define authorization, confirmation, idempotency, failure recovery, and audit evidence before enabling remote writes. The local contribution packet remains the source of reviewable evidence even when a remote Issue or Pull Request is created. Issue-backed and Discovery entries must converge before remote PR creation; Discovery evidence may serve as the contribution basis when policy permits it.
