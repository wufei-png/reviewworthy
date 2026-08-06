# Candidate menu and evidence matrix

The candidate artifact is intentionally not a scorecard. Each candidate records:

- contribution basis and project evidence;
- duplicate Issue/PR search and matches;
- value, bounded scope, review cost, verifiability, and risks;
- a recommendation: `plan_directly`, `seek_maintainer_signal`, `issue_only`, or `do_not_contribute`.

`reviewworthy candidate validate` rejects a single `score` or `confidence` field and prevents a candidate with duplicate matches from recommending direct contribution. The contributor and maintainer retain the selection decision.

After a signal-backed or Discovery candidate is selected, its Contribution Packet must record a structured [Contribution Signal](./contribution-signal.md). An existing Issue-backed candidate may use its Issue basis directly. A menu recommendation such as `seek_maintainer_signal` is not itself a signal and does not authorize implementation.

Record the selection and bind it explicitly:

```bash
reviewworthy candidate select .reviewworthy/candidates.json \
  --candidate-id candidate-001 --confirm
reviewworthy candidate bind \
  --menu .reviewworthy/candidates.json \
  --packet .reviewworthy/contribution.json
```

Binding copies the selected basis and records the menu snapshot and candidate ID in the Packet. It does not approve the Contribution Contract, and a `do_not_contribute` candidate cannot be bound.
