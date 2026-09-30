# Recover operations and complete the Skill-facing workflow

Status: Accepted — confirmed by the user on 2026-09-30.

## Context and evidence

The portfolio review evaluated commit `61b83d3449aaeb566eb4e0a9865b19022ce9855d`, which was also the checkout HEAD when this decision was prepared. The working tree was clean. Python 3.11.5 ran 238 unit tests successfully, and all 11 fixture evaluations passed. These checks establish a baseline; they do not establish live GitHub behavior or user outcomes.

Relevant current behavior:

- `cli.py` exposes `remote plan/create` and `signal publish plan/create`, but no explicit recovery command.
- `github.py` persists the original operation before creating an object. Its receipt reader rejects `pending`. Terminal receipts bridge read-after-write delay, but represent a past result rather than a fresh remote inspection.
- `policy.py` discovers most `.github` documents and Markdown under `docs`, excluding workflows and ADRs. The commit-tree reader uses line-delimited filenames. UTF-8 decode errors and aggregate scan costs are not consistently handled.
- `git.py` already hashes raw NUL-delimited records, but obtains `changed_files` and numstat through text lines.
- The Skill owns decisions, while some approved decisions still require direct Packet editing. `verify run` records a receipt but does not itself synchronize the verification flow-node result.
- The Action's base-policy projection handles conflicts and ambiguities explicitly; new policy failures must also reach enforcement instead of being lost in that projection.

## Selection rule

Existing project contracts and the user's requirements are constraints, not invitations to redesign the product. A proposal that conflicts with them and has not been explicitly authorized is excluded. A necessary, compatible proposal is included even when its original report priority was low. Priority determines order; it is not by itself an exclusion reason.

The user explicitly chose two adjustments during this review:

1. Policy option A: narrow default authoritative source discovery and allow additional documents to be explicitly listed.
2. Recovery option B: keep uncertainty blocked by default, but provide an explicitly confirmed retry after manual inspection when no matching remote object is found.

Only these adjustments supersede conflicting discovery/retry wording. They do not authorize unrelated changes to the product's trust boundaries.

## Decision

### Preserve the product and minimize Agent bookkeeping

Keep the Skill as the primary entry, the Packet private, the Evidence Summary minimal, and the Action read-only. GitHub.com public records remain the supported remote surface. Provider verification does not establish maintainer intent. The human still owns selection, approval, understanding, disclosure claims, and the exact public narrative.

Use existing Packet sections and artifacts. The CLI computes hashes, maintains flow-node results, and applies invalidation rules. Do not require an Agent to repeat a fact in a new envelope, compute an approval hash, maintain a second workflow state, or manually coordinate derived fields.

### Complete remote recovery

Recovery reads the original saved operation, not a newly rendered operation from the current Packet or moving branch refs. Remote inspection and local repair are the default. Supplying the matching operation ID may authorize completion of the original one-line Issue backlink; it does not authorize a new PR, a public-body rewrite, or a different operation.

Zero marker matches preserve uncertainty. Explicit retry is added to the existing create commands, requires their normal current readiness and identity checks plus the same operation ID, and makes one create attempt. It is restricted to pending object creation. A known PR URL, a failed backlink, malformed state, or multiple matches cannot become permission to create another object.

Keep the existing local lock. Do not infer stale locks from time; document manual removal only after the operator has established that no process owns the operation.

Inspect the newly returned object and perform a bounded post-create marker check. A visible duplicate is reported with its URLs; no object is silently selected or deleted. Zero results immediately after a successful create do not negate the successful response. Neither this check nor reconciliation guarantees global exactly-once behavior.

### Preserve the existing operation protocol

Retain current `0.3` operation IDs, markers, state paths, and readable state. Add representative contract fixtures so recovery work cannot accidentally change them. A small shared operation module may own state/recovery logic and isolate it from GitHub transport; a general provider platform is unnecessary.

Do not implement pre-0.3 readers or migrations, change marker spelling, or introduce speculative Packet/Signal 0.4 formats. These conflict with the current compatibility boundary or lack a required new semantic contract. Internal constants and tests may make the existing boundaries explicit without changing their wire representation.

### Bound and clarify policy input

Default sources are the current well-known root policy filenames and GitHub Issue/PR templates. Broad `.github` and `docs` content remains available to project orientation, but does not automatically create normative policy claims.

Add optional `[discovery].authoritative_documents`, an additive list of exact repository-relative file paths. No globs, implicit inheritance, or replacement of default sources. Structured rules continue to supplement silence rather than override conflicting human rules. The Action still reads the immutable base tree.

Use small fixed budgets and deterministic errors. Validate supported TOML keys and types at runtime using the standard library. Preserve the parser's already-supported aliases through explicit normalization; canonical schema validation and documented alias behavior must not drift silently. No mandatory policy version field is needed for this change.

Use NUL records for Git paths. Preserve the raw subject digest algorithm. Support valid UTF-8 paths representable by the existing path contract; unsupported byte encodings or spellings get a clear error instead of a new public path encoding or an uncaught decode failure.

### Complete the existing workflow interfaces

Provide typed recording/binding/approval operations for policy, basis, Contract, review profile, verification plan, ownership, AI assistance/disclosure, and narrative. Reuse candidate, Issue verification, Diff binding, verification execution, and understanding commands.

Repeated identical inputs are a no-op or an explicitly documented idempotent result. Material edits invalidate dependent evidence; commands never silently reapprove it. Narrative edits clear final confirmation. Human confirmations remain contributor claims, not authenticated proof of comprehension.

Add `start` only after these primitives work. It combines existing repository facts, policy, Brief, Packet and Issue verification, and presents the next decision without inventing architecture understanding, approval, duplicate disposition, or tests to execute.

### Include inexpensive necessary delivery work

Pin the repository's third-party Actions to verified immutable commits, disable checkout credential persistence, and give the composite Action clear Python/Git prerequisite failures. Keep runtime dependencies empty. Correct fixture-count drift and explain support/recovery boundaries. These are included despite their lower report priority.

Clarify the existing private security-reporting exception without adding a private Signal type or exposing advisory data. Maintainer-coordinated private work is not automatically processed through the public provider path. This does not replace the private-reporting requirement with a public Issue requirement.

## Excluded proposals and reasons

| Proposal | Reason for exclusion from this implementation |
|---|---|
| Earlier artifact readers, Packet/Signal 0.4 migration framework | Current 0.3 explicitly rejects older formats; this scope has no required new artifact format. |
| Mandatory capabilities/extensions/policy-version data | No selected operation needs them, and mandatory additions would increase Agent bookkeeping. |
| Second provider or full adapter/capability registry | No concrete second-platform workflow or acceptance target; preserve the current supported surface. A shared recovery seam is included. |
| Discussion publication | Expands the current Issue-only publication contract; not required for the selected Issue-to-PR journey. Discussion read verification remains supported. |
| Automatic maintainer authority/lifecycle inference | Conflicts with the Skill-owned judgment and orthogonal authority boundary. |
| New observation artifact | No selected workflow consumes it; existing provider facts and human interpretation suffice. |
| Security Advisory API or private basis protocol | Expands the public-record contract and security handling; current private reporting is out of band. |
| Cross-host lock service or exactly-once guarantee | Unnecessary infrastructure, conflicts with the explicitly limited guarantee, and adds little value relative to its cost. Bounded duplicate detection is included. |
| Large Diagnostic schema, full environment-product test matrix, new audit fields | Existing diagnostics and focused differential/fault tests cover the selected contracts with less data and maintenance. |
| Session export/import or cloud synchronization | No selected workflow requires portability beyond the existing local state. |

These are exclusions by contract or necessity, not a queue labelled “low priority.” New user authorization and a concrete need would require a separate decision.

## Consequences and implementation

The two authorized adjustments change policy discovery and opt-in retry behavior. Update their active references, Skill instructions, threat model and changelog alongside the relevant implementation. Do not rewrite historical release evidence as if the new behavior existed at its original release.

Execution is defined in [the six-session implementation plan](../../references/implementation-plan-2026-09-30.md). Each session reads the shared queue and its own plan, uses implement-in-stages for verified local commits, then runs delegated-change-review and records adjudicated findings and verified fixes. The plan includes contract tests, real local Git fixtures, interruption/failure cases, and handoff records; live remote mutations and publication require separate authorization.
