# Contribution Signal

A Candidate Menu describes possible work. A selected Contribution Packet must record the signal that makes the work actionable.

## Signal kinds

- `issue`: an existing project issue or explicitly requested fix;
- `maintainer-request`: a request recorded by a maintainer or project actor;
- `accepted-proposal`: an accepted design or project proposal;
- `discussion`: a project discussion whose outcome supports the contribution;
- `reproducible-evidence`: a reproducible failure or gap that the repository policy explicitly permits as sufficient Discovery evidence.

Each signal records a reference, status, publication state, and evidence. An external `issue`, `maintainer-request`, `accepted-proposal`, or `discussion` signal must point to a publicly created record (`published: true`). A local Issue/Discussion draft is not yet a Signal; its pre-publication JSON may have an empty reference and is intentionally outside the published Signal JSON Schema until `signal publish create` succeeds. A `reproducible-evidence` signal may remain unpublished and does not require a maintainer reply, but it needs evidence and explicit policy authorization before remote readiness. `confirmed_by` and `confirmed_at` record an optional explicit project response; confirmation is not required to implement or submit.

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

For an external signal, verify the public record without changing the artifact:

```bash
reviewworthy signal verify .reviewworthy/contribution-signal.json
```

Use `--record` only after a successful verification to persist the exact reference/provider result required by remote readiness:

```bash
reviewworthy signal verify .reviewworthy/contribution-signal.json --record
```

Reviewworthy does not interpret an open Issue, a comment, or a closed record as maintainer approval. To publish a local Issue draft, first preview the explicit operation and then confirm that exact operation ID:

```bash
reviewworthy signal publish plan .reviewworthy/contribution-signal.json \
  --repo OWNER/REPO --title "Candidate request" --body-file signal.md
reviewworthy signal publish create .reviewworthy/contribution-signal.json \
  --repo OWNER/REPO --title "Candidate request" --body-file signal.md \
  --confirm-operation-id rw-...
```

Publication uses the same marker search, pending record, receipt, and reconciliation rules as other Issue writes. It updates the local Signal only after the remote result is recorded; a repeated create reuses the receipt instead of creating a duplicate.
