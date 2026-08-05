# Persist local receipts for remote-write retry idempotency

Remote marker lookup is necessary but not sufficient because GitHub can temporarily lag a successful create in list/API responses. After a successful Issue or Pull Request creation, Reviewworthy persists an ignored local receipt keyed by the rendered operation ID; an immediate retry returns the recorded remote result without issuing a second create request. A missing, malformed, or mismatched receipt is a reconciliation error rather than permission to retry blindly.

## Considered Options

- Trust a post-create remote list response immediately.
- Persist a local operation receipt and use remote lookup for reconciliation.
- Retry the create request when the remote list does not yet show the object.

## Consequences

The local packet directory contains ignored operational state. Users must preserve that state while recovering an uncertain write, or reconcile the marker against GitHub before retrying from another checkout.
