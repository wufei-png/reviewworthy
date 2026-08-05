# Persist local receipts for remote-write retry idempotency

Remote marker lookup is necessary but not sufficient because GitHub can temporarily lag a successful create in list/API responses. Reviewworthy persists a pending local operation record immediately before a create, then replaces it with an ignored local receipt after a successful Issue or Pull Request creation. An immediate retry returns the recorded remote result without issuing a second create request. A pending, missing, malformed, incomplete, or mismatched record is a reconciliation error rather than permission to retry blindly.

## Considered Options

- Trust a post-create remote list response immediately.
- Persist a local operation receipt and use remote lookup for reconciliation.
- Retry the create request when the remote list does not yet show the object.

## Consequences

The local packet directory contains ignored operational state. Users must preserve that state while recovering an uncertain write, or reconcile the marker against GitHub before retrying from another checkout.
