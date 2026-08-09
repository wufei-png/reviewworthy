# Threat model

Reviewworthy is one contributor-first product with two trust surfaces: a local contributor workflow and an optional repository-side Evidence Action. They share domain contracts but do not assign the same authority to every artifact.

## Trust classes

Runner-owned facts are GitHub event repository identity, base/head object IDs, the recomputed merge-base subject, and policy read from the immutable base tree. In `evidence-enforce`, positive machine policy authority comes only from base-tree `.reviewworthy/policy.toml`. Explicit document prohibitions, conflicts, and ambiguities may block; positive document parsing remains advisory.

Contributor claims include local verification receipts, Ownership Check, Contract approval, Understanding answers, and AI disclosure. Packet `0.3` binds and validates these claims for contributor self-discipline, but the Action does not describe unsigned local evidence as independently authenticated CI fact.

Advisory evidence includes Candidate recommendations, duplicate-work disposition, and human interpretation of project documents. It informs decisions without becoming remote authorization.

## Protected boundaries

- The full Packet is Git-private local state; only the minimal Evidence Summary enters the PR Body.
- Packet, Signal, receipt, pending state, and remote marker `0.3` do not read, recognize, migrate, or reconcile older formats.
- Action policy is read from the base commit, so a Pull Request cannot authorize itself by changing policy on its head.
- Remote writes require confirmation of the exact rendered operation ID. Current pending/receipt state is versioned and multiple marker matches stop for reconciliation.
- Git, verification, and `gh` commands have time and captured-output bounds. Artifact replacement is atomic within one filesystem.

## Non-guarantees

Reviewworthy does not sign local receipts, prove that a human understood an answer, infer maintainer intent from record state, make GitHub writes globally exactly-once, or replace repository-owned CI and branch protection. A maintainer requiring independently authenticated test results must run trusted CI or verify an attestation outside the contributor-local receipt contract.

Do not put secrets, vulnerability details, credentials, or unnecessary personal information into a Packet or Evidence Summary. Use the private security-reporting path for suspected vulnerabilities.
