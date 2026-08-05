# Policy discovery

Repository-authored human-facing documents are the semantic authority. Reviewworthy inspects `README`, `CONTRIBUTING`, `SECURITY`, `AGENTS`, `.github` templates, and relevant Markdown under `docs/`.

`.reviewworthy/policy.toml` is an optional structured supplement. It helps automation consume rules that the repository has already stated or makes explicit where the documents are silent. It cannot silently override a human-facing rule.

If two sources disagree, emit `policy_conflict` and stop remote writes. If a claim is absent, use Conservative mode rather than inferring permission.

The first schema supports:

```toml
[ai]
allowed = true
disclosure_required = true
disclosure_locations = ["pr_body"]
disclosure_stages = ["implementation", "verification"]

[contribution]
issue_required = false
discovery_evidence_allowed = true
good_first_issue_ai_allowed = true

[pr]
human_narrative_required = true
draft_required = false

[security]
private_reporting_required = true
```
