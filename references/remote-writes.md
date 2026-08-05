# Remote writes

Remote writes are explicit operations, not incidental side effects.

The CLI first renders the exact target, title, Body, base/head, permissions, and stable operation ID. The user confirms that operation ID. If any rendered field changes, the old confirmation is invalid.

The operation ID is embedded in the Body as:

```text
<!-- reviewworthy:operation-id=rw-... -->
```

Before creating an Issue or Pull Request, the `gh` adapter searches existing objects for the marker. If the previous result is uncertain, it stops for reconciliation rather than retrying blindly.

After a successful create, the CLI stores an ignored local operation receipt under `.reviewworthy/local/operations/`. This receipt bridges GitHub's short read-after-write delay: an immediate retry returns `already_exists` without issuing a second create request. A malformed or mismatched receipt is a reconciliation error, not permission to retry.
