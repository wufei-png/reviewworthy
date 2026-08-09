# Contribution Signal 0.3

A Candidate Menu describes possible work. A selected Contribution Packet records the signal that makes the work actionable. Signal `0.3` is a clean break: older Signal fields and versions are rejected rather than read, migrated, or coordinated.

## Independent axes

- `record_type`: `issue`, `pull_request`, `discussion`, or `local_evidence`;
- `claim_type`: `bug_report`, `maintainer_request`, `accepted_proposal`, or `reproducible_evidence`;
- `lifecycle`: `pending`, `confirmed`, `rejected`, or `expired`;
- `verification`: provider evidence tied to the exact reference and record type;
- `authority`: `contributor`, `maintainer`, or `repository`, with actor and assertion time where required.

These axes are deliberately not collapsed. A Discussion can carry an accepted-proposal claim without making every Discussion an accepted proposal. A public Issue can remain pending after provider verification. Confirmed maintainer-request and accepted-proposal claims require maintainer or repository authority; an open, closed, or verified record alone is not approval.

External records require a canonical matching GitHub URL. Issue and Pull Request verification use the REST API; Discussion verification uses GitHub GraphQL. `local_evidence` must carry a `reproducible_evidence` claim and non-empty evidence. Discovery use also needs explicit repository policy authorization.

Create and validate a current Signal:

```bash
reviewworthy signal init \
  --record-type issue \
  --claim-type maintainer_request \
  --reference https://github.com/OWNER/REPO/issues/123 \
  --output .reviewworthy/contribution-signal.json
reviewworthy signal validate .reviewworthy/contribution-signal.json
```

Verify an external record without changing the artifact:

```bash
reviewworthy signal verify .reviewworthy/contribution-signal.json
```

Use `--record` only after success to persist verification required by remote readiness:

```bash
reviewworthy signal verify .reviewworthy/contribution-signal.json --record
```

Issue publication remains a separate explicit operation. A pre-publication Issue Signal may have an empty reference and is invalid for ordinary readiness until creation succeeds:

```bash
reviewworthy signal publish plan .reviewworthy/contribution-signal.json \
  --repo OWNER/REPO --title "Candidate request" --body-file signal.md
reviewworthy signal publish create .reviewworthy/contribution-signal.json \
  --repo OWNER/REPO --title "Candidate request" --body-file signal.md \
  --confirm-operation-id rw-...
```

Publication identity is recorded by `publication_subject_id` and `publication`; there is no `published` compatibility flag. Publication uses current `0.3` markers and operation receipts only. Discussion publication and maintainer-response interpretation are not implemented.
