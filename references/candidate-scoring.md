# Candidate menu and evidence matrix

The candidate artifact is intentionally not a scorecard. Each candidate records:

- contribution basis and project evidence;
- duplicate Issue/PR search, matches, and an explicit disposition;
- value, bounded scope, review cost, verifiability, and risks;
- a recommendation: `plan_directly`, `seek_maintainer_signal`, `issue_only`, or `do_not_contribute`.

`reviewworthy candidate validate` rejects a single `score` or `confidence` field and requires one of `exact_duplicate`, `potential_duplicate`, `related`, `not_duplicate`, `stale`, or `superseded` (with `superseded_by`). `exact_duplicate` blocks implementation; `potential_duplicate` permits investigation but blocks implementation/readiness until resolved. `related`, `not_duplicate`, `stale`, and `superseded` do not create an automatic duplicate block. The CLI records the disposition supplied by the contributor/Skill; it does not infer relatedness.

After a signal-backed or Discovery candidate is selected, its Contribution Packet must record a structured [Contribution Signal](./contribution-signal.md). An existing Issue-backed candidate may use its Issue basis directly. A menu recommendation such as `seek_maintainer_signal` is not itself a signal and does not authorize implementation.

`do_not_contribute` is a hard stop. `issue_only` and `seek_maintainer_signal` are advisory recommendations: a human may explicitly transition either one to `plan_directly` with a non-empty reason and confirmation:

```bash
reviewworthy candidate transition \
  --packet .git/reviewworthy/v0.3/contributions/contribution-001/packet.json \
  --to plan_directly \
  --reason "The verified public Issue now bounds the change." --confirm
```

The transition records human confirmation but does not bypass the later basis gate. `issue_only` still needs a verified Issue; `seek_maintainer_signal` still needs a public, successfully verified Signal. A pending Signal is acceptable after verification; maintainer confirmation is not inferred or required.

Record the selection and bind it explicitly:

```bash
reviewworthy candidate select .reviewworthy/candidates.json \
  --candidate-id candidate-001 --confirm
reviewworthy candidate bind \
  --menu .reviewworthy/candidates.json \
  --packet .git/reviewworthy/v0.3/contributions/contribution-001/packet.json
```

Binding copies the selected basis and records the menu snapshot, candidate ID, repository, recommendation, and duplicate disposition in the Packet. It does not approve the Contribution Contract. Only a `do_not_contribute` recommendation prevents binding; `issue_only` and `seek_maintainer_signal` remain valid planning choices until their explicit transition and later Issue/Signal gates are satisfied. Packet `0.3` does not accept or migrate older bound-candidate records.
