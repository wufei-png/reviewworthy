# Repository workflows route external-contribution enforcement

Reviewworthy's mandatory contribution gates apply to External Contributions. A Maintainer Change is authorized through repository governance and may be pushed directly without a Reviewworthy PR. The repository still owns engineering standards, CI, release evidence, and security handling for those changes. Workflow configuration decides which events and actors invoke Reviewworthy enforcement; the core Action validates supplied evidence but does not infer maintainer identity or permission.

## Considered Options

- Require every change, including Maintainer Changes, to dogfood the full Issue, Packet, and PR protocol.
- Make the core Action query provider permissions and exempt actors it classifies as maintainers.
- Keep authorization and event routing in repository governance while the portable Action remains a deterministic evidence checker.

## Consequences

External contributors receive a consistent fail-closed evidence path without turning maintainer authority into a provider-specific runtime guess. Maintainers can use direct push when their governance permits it, and ordinary push CI can still run. Consuming repositories that want stronger controls may add branch protection, required checks, or actor-aware workflow conditions, but those settings are not created or assumed by Reviewworthy.
