# Candidate menu and evidence matrix

The candidate artifact is intentionally not a scorecard. Each candidate records:

- contribution basis and project evidence;
- duplicate Issue/PR search, matches, and an explicit disposition;
- value, bounded scope, review cost, verifiability, and risks;
- a recommendation: `plan_directly`, `seek_maintainer_signal`, `issue_only`, or `do_not_contribute`.

`reviewworthy candidate validate` rejects a single `score` or `confidence` field and requires one of `exact_duplicate`, `potential_duplicate`, `related`, `not_duplicate`, `stale`, or `superseded` (with `superseded_by`). `exact_duplicate` blocks implementation; `potential_duplicate` permits investigation but blocks implementation/readiness until resolved. `related`, `not_duplicate`, `stale`, and `superseded` do not create an automatic duplicate block. The CLI records the disposition supplied by the contributor/Skill; it does not infer relatedness.

After a signal-backed or Discovery candidate is selected, its Contribution Packet must record a structured [Contribution Signal](./contribution-signal.md). An existing Issue-backed candidate may use its Issue basis directly. A menu recommendation such as `seek_maintainer_signal` is not itself a signal and does not authorize implementation.

Record the selection and bind it explicitly:

```bash
reviewworthy candidate select .reviewworthy/candidates.json \
  --candidate-id candidate-001 --confirm
reviewworthy candidate bind \
  --menu .reviewworthy/candidates.json \
  --packet .reviewworthy/contribution.json
```

Binding copies the selected basis and records the menu snapshot, candidate ID, repository, recommendation, and duplicate disposition in the Packet. It does not approve the Contribution Contract. Only a `do_not_contribute` recommendation prevents binding; `issue_only` and `seek_maintainer_signal` remain valid planning choices, while their later Issue/Signal gates still apply.
