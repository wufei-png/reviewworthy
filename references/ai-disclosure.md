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

Record the existing `ai_assistance` section with:

```bash
reviewworthy packet ai record --packet "$PACKET" --input ai-assistance.json --json
```

The JSON contains `used`, `stages` (`name`, `level`, boolean `human_verified`),
and `disclosure` (`text`, `locations`, boolean `human_confirmed`). The command
checks policy-required stages/locations and rejects verification overclaims.
It never fills in human verification. Changing assistance claims, disclosure text,
or locations clears the prior disclosure confirmation and final narrative approval.
Re-recording the same content with an explicit `human_confirmed: true` claim can
confirm that disclosure; final narrative confirmation also explicitly approves the
current disclosure. Material implementation/verification changes reset the stage
verification claims and disclosure confirmation, requiring human review again.
