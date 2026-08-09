# Derived status and isolated operation state

## Decision

`status` and `next` derive contributor progress from the current Packet and its readiness blockers; no separate workflow-state file is authoritative. Remote-write pending state and receipts are local implementation records under `local/v0.3/operations/` and carry `state_version=0.3`.

Packet `0.3` ignores every older Packet, Signal, receipt, pending-state path, and remote marker. It does not migrate or reconcile those formats. Multiple matches for the current remote marker are ambiguous and stop the write for explicit reconciliation.

Subprocesses used for Git, verification, and GitHub access have explicit time and captured-output bounds. Durable artifact replacement uses an atomic same-directory rename.

## Consequences

- Contributor progress cannot drift from the Packet because it is recomputed rather than stored.
- An upgrade cannot accidentally resume an older pending operation or accept an older receipt.
- Retry safety fails closed on ambiguous current markers.
- Hung or noisy child processes cannot consume unbounded execution time or captured output.
