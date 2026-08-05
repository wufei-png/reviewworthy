# Treat unknown contribution policy as conservative

When a repository's contribution and AI-assistance policy cannot be established confidently, Reviewworthy enters Conservative mode for contribution and remote-write decisions: it preserves human approval, requires clear AI-assistance disclosure, and does not infer permission for a risky action. Read-only reporting may still surface the unknown policy without treating it as a deterministic violation. This favors predictable maintainer safety over maximum automation when the repository has not stated its rules.

## Considered Options

- Infer permissive defaults from common GitHub conventions.
- Stop every task when policy is incomplete.
- Continue only with conservative controls and explicit human approval.

## Consequences

Policy inspection must distinguish `allowed`, `prohibited`, `required`, and `unknown` rather than collapsing missing evidence into permission. The CLI and Skill must surface the fallback in the contribution packet.
