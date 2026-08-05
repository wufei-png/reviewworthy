# Policy-aware AI disclosure

Structured policy may specify `disclosure_locations` and `disclosure_stages` under `[ai]` in `.reviewworthy/policy.toml`:

```toml
[ai]
allowed = true
disclosure_required = true
disclosure_locations = ["pr_body"]
disclosure_stages = ["implementation", "verification"]
```

The packet records stage-level assistance and human verification, then stores a disclosure text, its locations, and contributor confirmation. `reviewworthy disclosure render --packet ...` renders a policy-aware snippet. Unknown policy uses Conservative mode and defaults to a human-confirmed PR Body disclosure.
