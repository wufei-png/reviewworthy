# Keep the full Packet local and publish a minimal PR Evidence Summary

Reviewworthy `0.3` stores the full Contribution Packet under Git-private `.git/reviewworthy/v0.3/` state. A Pull Request publishes one versioned, machine-readable Evidence Summary in its Body. The Summary contains repository and contribution Diff identity plus explicitly labelled contributor claims; it omits private understanding answers, local paths, raw receipts, timestamps, and logs.

The contribution subject is fingerprinted from canonical merge-base-to-head Git content records: path bytes, status, file modes, and old/new blob identities. Commit identity, patch presentation, timestamps, and Reviewworthy state are not part of `subject_digest`. The PR Action recomputes this subject from runner-owned base/head objects and never reads a Packet from the checkout.

## Considered Options

- Commit the full Packet and permanently retain it in the target repository.
- Support committed Packets and PR Body evidence as equal canonical modes.
- Keep one private local Packet and publish one minimal public projection.

## Consequences

The default workflow does not dirty the contribution worktree or require an upstream repository to accept Reviewworthy files. The public Action can verify repository identity and contribution content while presenting local verification and ownership only as contributor claims. Local Packet retention remains the contributor's responsibility. A PR Body with absent, duplicate, unmatched, malformed, or non-current Evidence Summary markers cannot pass `evidence-enforce`.

Version `0.3` has no compatibility behavior: it does not interpret, migrate, or reconcile earlier artifact or marker formats.
