# Contribution Signal

A Candidate Menu describes possible work. A selected Contribution Packet must record the signal that makes the work actionable.

## Signal kinds

- `issue`: an existing project issue or explicitly requested fix;
- `maintainer-request`: a request recorded by a maintainer or project actor;
- `accepted-proposal`: an accepted design or project proposal;
- `discussion`: a project discussion whose outcome supports the contribution;
- `reproducible-evidence`: a reproducible failure or gap that the repository policy explicitly permits as sufficient Discovery evidence.

Each signal records a reference, status, and evidence. `maintainer-request`, `accepted-proposal`, and `discussion` also record the confirming project actor and time. A reproducible-evidence signal does not require a maintainer reply, but it must be confirmed and policy-authorized.

## Lifecycle gate

Discovery candidates may be displayed, compared, and turned into an Issue or Discussion draft while their signal is `pending`. They cannot enter implementation or remote readiness until the structured signal is `confirmed`.

Issue-backed entries may use their existing Issue reference directly. If they rely on a separate maintainer request or proposal, the packet records the corresponding signal object instead of treating a free-form label as proof.

Create and validate a signal artifact with:

```bash
reviewworthy signal init --kind maintainer-request \
  --reference https://github.com/OWNER/REPO/issues/123 \
  --output .reviewworthy/contribution-signal.json
reviewworthy signal validate .reviewworthy/contribution-signal.json --require-confirmed
```
