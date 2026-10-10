# Fixture evaluations

These fixtures exercise deterministic workflow boundaries without a network provider or an LLM:

- policy prohibition, including the concrete readiness blocker;
- duplicate-work disposition;
- Issue-required contributions;
- good-first-issue AI restrictions;
- scope expansion;
- unverifiable results;
- stale understanding material;
- human-owned PR narrative;
- Discovery work without a structured Contribution Signal;
- stale Orientation after the selected basis changes;
- Action enforcement without a current public Evidence Summary.

Run them with:

```bash
PYTHONPATH=src python -m reviewworthy eval run
```

Fixtures are release-boundary checks, not a claim that a successful run proves a contribution is reviewworthy.
The separate [offline pilot harness](pilot/README.md) replays four Agent decision
cases with real local Git and closed provider mocks. It keeps manual samples,
simulation and externally observed model runs distinct and leaves semantic scoring
to human review. Run it with `reviewworthy pilot run`, not `reviewworthy eval run`.
The command reports the current fixture count; the fixture directory is the source
of truth, so adding a case does not require maintaining a second numeric total here.
