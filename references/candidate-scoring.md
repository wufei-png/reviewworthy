# Candidate menu and evidence matrix

The candidate artifact is intentionally not a scorecard. Each candidate records:

- contribution basis and project evidence;
- duplicate Issue/PR search and matches;
- value, bounded scope, review cost, verifiability, and risks;
- a recommendation: `plan_directly`, `seek_maintainer_signal`, `issue_only`, or `do_not_contribute`.

`reviewworthy candidate validate` rejects a single `score` or `confidence` field and prevents a candidate with duplicate matches from recommending direct contribution. The contributor and maintainer retain the selection decision.

After a candidate is selected, its Contribution Packet must record a structured [Contribution Signal](./contribution-signal.md). A menu recommendation such as `seek_maintainer_signal` is not itself a signal and does not authorize implementation.
