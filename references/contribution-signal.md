# Contribution Signal

A Candidate Menu describes possible work. A selected Contribution Packet must record the signal that makes the work actionable.

## Signal kinds

- `issue`: an existing project issue or explicitly requested fix;
- `maintainer-request`: a request recorded by a maintainer or project actor;
- `accepted-proposal`: an accepted design or project proposal;
- `discussion`: a project discussion whose outcome supports the contribution;
- `reproducible-evidence`: a reproducible failure or gap that the repository policy explicitly permits as sufficient Discovery evidence.

Each signal records a reference, status, publication state, and evidence. An external `issue`, `maintainer-request`, `accepted-proposal`, or `discussion` signal must point to a publicly created record (`published: true`). A local Issue/Discussion draft is not yet a Signal. A `reproducible-evidence` signal may remain unpublished and does not require a maintainer reply, but it needs evidence and explicit policy authorization before remote readiness. `confirmed_by` and `confirmed_at` record an optional explicit project response; confirmation is not required to implement or submit.

## Lifecycle gate

Discovery candidates may be displayed, compared, and turned into a local Issue or Discussion draft before implementation. After the external record is publicly created, its Signal may remain `pending` while the maintainer has not responded; pending does not block implementation or remote readiness. Rejected or expired signals do block progression.

Issue-backed entries may use their existing Issue reference directly. If they rely on a separate maintainer request or proposal, the packet records the corresponding signal object instead of treating a free-form label as proof.

Create and validate a signal artifact with:

```bash
reviewworthy signal init --kind maintainer-request \
  --reference https://github.com/OWNER/REPO/issues/123 \
  --published \
  --output .reviewworthy/contribution-signal.json
reviewworthy signal validate .reviewworthy/contribution-signal.json
```
