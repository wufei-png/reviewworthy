# Orthogonal Signals and base-tree Action policy authority

Contribution Signal `0.3` represents record type, claim type, lifecycle, verification, and authority as independent axes. Issue, Pull Request, Discussion, and local evidence describe where a record exists; bug report, maintainer request, accepted proposal, and reproducible evidence describe what is claimed. Provider verification establishes existence and identity, not maintainer endorsement. Confirmed maintainer claims therefore require separate authority evidence.

The repository Action evaluates policy only from the immutable pull-request base commit. Human-facing repository documents remain primary guidance for the contributor workflow. For Action enforcement, positive natural-language claims are advisory and only `.reviewworthy/policy.toml` supplies positive machine authority. Explicit prohibitions, conflicts, and ambiguities remain deterministic blockers. Pull-request head changes cannot rewrite the policy used to judge that same Pull Request.

## Rejected alternatives

- Keep the old `kind`, `status`, and `published` fields and infer the missing dimensions.
- Treat a verified or closed public record as maintainer confirmation.
- Read policy from the pull-request checkout or grant machine permission from positive natural-language parsing.
- Use a guessed REST endpoint for GitHub Discussions.

## Consequences

All older Signal artifacts are invalid and receive no migration path. Discussion references are verified read-only through GitHub GraphQL, while Discussion publication remains out of scope. The Action exposes structured base policy as `machine_authority` and document claims as `document_advisory`, making the trust boundary visible in its result.
