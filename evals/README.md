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
The command reports the current fixture count; the fixture directory is the source
of truth, so adding a case does not require maintaining a second numeric total here.
