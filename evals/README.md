# Fixture evaluations

These eight fixtures exercise deterministic workflow boundaries without a network provider or an LLM:

- policy prohibition, including the concrete readiness blocker;
- duplicate-work disposition;
- Issue-required contributions;
- good-first-issue AI restrictions;
- scope expansion;
- unverifiable results;
- stale understanding material;
- human-owned PR narrative.
- Discovery work without a structured Contribution Signal.

Run them with:

```bash
PYTHONPATH=src python -m reviewworthy eval run
```

Fixtures are release-boundary checks, not a claim that a successful run proves a contribution is reviewworthy.
