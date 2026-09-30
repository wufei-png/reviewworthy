# Policy discovery

Repository-authored human-facing documents are the semantic authority. Default sources are root `README.md`, `README`, `CONTRIBUTING.md`, `CONTRIBUTING`, `AGENTS.md`, and `SECURITY.md`, plus Issue/PR template files and directories under `.github` (upper/lowercase template names are supported). Other `.github` files and `docs` are not automatically policy sources. Project Brief orientation still discovers project documents separately.

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

Add exact repository-relative documents to the defaults with:

```toml
[discovery]
authoritative_documents = ["docs/contributing.md"]
```

These paths must name readable UTF-8 regular files. Paths are literal, so wildcard punctuation in a filename is not expanded. Directory and glob expansion are unsupported; a missing explicit source blocks policy inspection. Unknown keys and invalid values produce ordered diagnostics with source/key paths. The portable schema describes canonical fields; the CLI also accepts existing boolean top-level aliases, `ai.assistance_allowed`, `contribution.ai`, nested `ai.disclosure.locations/stages`, and `allowed = "allowed"`/`"prohibited"` before validation. Opposed alias values are invalid. No policy version field is required.

Local inspection and immutable commit-tree inspection use the same selection, validation, claim and provenance rules. Sources and their parent components must not be symlinks; Git symlink/submodule modes are rejected. Text must be UTF-8 without NUL bytes. Fixed budgets include structured policy: 128 selected sources, 1 MiB per source, 8 MiB in total. The bounded structured file is read first to discover explicit paths; all selected document counts and sizes are checked before document reading or claim parsing. A size change during reading also blocks inspection. Git enumeration and blob reads have bounded subprocess capture and time limits.

Source/path/read/decode/limit failures produce `policy_*` diagnostics, Conservative posture and hard stops, with no usable positive permission. Contributor readiness receives these blockers; the Action projects them as `base_policy_*` violations in `evidence-enforce` and reports them as unknowns in non-blocking `report`. Only the base commit's discovery list controls the Action scan. Diagnostics contain paths and short messages, without full source text.
