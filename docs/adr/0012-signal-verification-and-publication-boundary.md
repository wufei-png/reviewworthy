# Keep public Signal verification read-only and publication explicit

Reviewworthy distinguishes a public external Signal record from a maintainer response. The CLI verifies a supported GitHub reference without mutation by default; an explicit `--record` step may persist the successful provider evidence, tied to the exact reference, for remote readiness. It never infers approval. Turning a local Discovery draft into a public Issue is a separate, explicit operation that requires an operation ID and reuses the existing pending-record and receipt protocol.

## Considered Options

- Infer Signal confirmation from Issue state, comments, or closure.
- Require all Discovery work to wait for a maintainer response.
- Verify public references read-only, allow valid pending Signals, and publish only through an explicit Issue operation.

## Consequences

The workflow can progress on a real public signal without pretending that a maintainer has endorsed the implementation. Provider verification is required evidence rather than a maintainer judgment. Issue publication is auditable and retry-safe, while Discussion publication and response interpretation remain separate future provider work.
