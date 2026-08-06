# Remote writes

Remote writes are explicit operations, not incidental side effects.

The CLI first renders the exact target, title, Body, base/head, permissions, and stable operation ID. The user confirms that operation ID. If any rendered field changes, the old confirmation is invalid.

The operation ID is embedded in the Body as:

```text
<!-- reviewworthy:operation-id=rw-... -->
```

Before creating an Issue or Pull Request, the `gh` adapter searches existing objects for the marker. If the previous result is uncertain, it stops for reconciliation rather than retrying blindly.

Remote readiness also requires an approved Contribution Contract, a valid non-rejected Contribution Signal for Discovery or signal-backed work, a recorded successful public-reference verification for external Signals, passed Orientation and Assessment, verification commands/evidence, and deterministic scope/budget checks. Maintainer confirmation is optional. Reproducible Discovery evidence additionally needs an explicit policy allowance. If policy requires a Draft PR, the operation includes that state and invokes `gh pr create --draft`.

Immediately before a create, the CLI persists a pending operation record. After a successful create it replaces that record with an ignored local operation receipt under `.reviewworthy/local/operations/`. The receipt bridges GitHub's short read-after-write delay: an immediate retry returns `already_exists` without issuing a second create request. A pending, malformed, incomplete, or mismatched record is a reconciliation error, not permission to retry.

`signal publish` is an Issue-only remote operation for turning a local Discovery draft into a public Signal. It has its own stable operation subject and updates the Signal artifact only after the same receipt protocol succeeds. Discussion publication is intentionally not inferred from or silently substituted for an Issue publication.
