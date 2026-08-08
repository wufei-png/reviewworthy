# Policy discovery

Repository-authored human-facing documents are the semantic authority. Reviewworthy inspects `README`, `CONTRIBUTING`, `SECURITY`, `AGENTS`, `.github` templates, and relevant Markdown under `docs/`.

`.reviewworthy/policy.toml` is an optional structured supplement. It helps automation consume rules that the repository has already stated or makes explicit where the documents are silent. It cannot silently override a human-facing rule.

Explicit positive and negative statements normalize to `true` and `false`. If two sources disagree, emit `policy_conflict`; if one source makes both claims, emit `policy_ambiguity` instead. Both stop remote writes. If a claim is absent, use Conservative mode rather than inferring permission.

The `good_first_issue_ai_allowed` claim is applied only to labels captured by a successful Issue or Issue-signal verification. Free-form `basis.labels` is not trusted. Pull-request creation revalidates the live Issue labels before any remote write.

`policy inspect` emits `claim_records` for each known claim. Each record has a `true`, `false`, or `unknown` state, the selected value, and provenance with source path, line range, and an excerpt hash. Document provenance points to the actual matched policy statement. Structured TOML provenance points to the parsed table/key that supplied the value, so an unrelated same-named key cannot become the evidence anchor. A structured claim can fill a silent document, but it does not hide document evidence. Conflicting or internally ambiguous claims become `unknown` and carry their distinct hard-stop code.

The structured AI `allowed` claim may be `true`, `false`, or `"unknown"`; `"unknown"` is normalized to Conservative mode and never treated as permission.

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
