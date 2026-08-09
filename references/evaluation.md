# Fixture evaluations

`reviewworthy eval run` executes the eleven provider-free fixtures under `evals/fixtures`. They cover policy prohibition, duplicate work, Issue requirements, good-first-issue restrictions, scope expansion, unverifiable results, stale understanding, human-owned narrative requirements, the Discovery Signal gate, stale Orientation, and Action enforcement when the Evidence Summary is missing.

Packet fixtures assert the exact sorted `blocker_codes` set and a `ready`/`blocked` result. Action fixtures assert the exact sorted `violation_codes` set plus both `conclusion` and `passed`/`failed` result. The evaluator deliberately checks these narrow outcomes instead of snapshotting the complete JSON response, so unrelated explanatory fields can evolve without hiding a changed gate.

The evaluator is a regression harness for deterministic boundaries. A passing run does not prove that a contribution is valuable, understood, or acceptable to a maintainer; those remain Skill and human decisions.
