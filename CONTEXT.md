# Reviewworthy Domain Language

This glossary defines the language for preparing AI-assisted open-source contributions that respect project policy, contributor ownership, and maintainer review capacity.

## Product and responsibility

**Reviewworthy**:
A contribution workflow whose success is measured by whether a change is needed, understandable, verifiable, and worth a maintainer's review time.
_Avoid_: PR generator, AI code bot

**Maintainer-first**:
A principle that protects maintainer attention by checking project need, reviewability, and policy before maximizing automation.
_Avoid_: maintainer-only, maintainer-over-contributor

**Human-owned contribution**:
A contribution for which a person can explain the problem, scope, design, evidence, risks, and public narrative, regardless of how AI assisted the work.
_Avoid_: human-written, AI-free contribution

## Contribution lifecycle

**Contribution candidate**:
A possible change supported by project evidence that has not yet been selected and approved for implementation.
_Avoid_: opportunity, random improvement

**Contribution signal**:
A status-bearing, recorded contribution basis, such as a public issue, maintainer request, accepted proposal, discussion, or a reproducible failure that satisfies the project's contribution policy. External signals must be publicly recorded; reproducible evidence may remain unpublished. Maintainer confirmation is optional, while rejected or expired signals cannot progress.
_Avoid_: agent enthusiasm, inferred demand

**Contribution basis**:
The recorded evidence that justifies doing a contribution; it may be an existing issue or signal, or reproducible Discovery evidence when the project policy treats that evidence as sufficient.
_Avoid_: justification paragraph, prompt context

**Issue-backed entry**:
An entry path that starts with an existing issue or explicit project request and can move directly into project understanding and a contribution contract.
_Avoid_: ticket mode

**Discovery mode**:
A contribution path in which a possible change is found through repository or project analysis and must produce a recorded contribution basis before entering the shared implementation flow.
_Avoid_: autonomous mode, opportunistic PR mode

**Contribution contract**:
The shared agreement that fixes a selected contribution's problem, non-goals, scope, invariants, design, validation, risks, and success criteria before implementation.
_Avoid_: implementation prompt, task prompt

**Contribution packet**:
The reviewable set of policy findings, project understanding, contribution contract, change evidence, validation evidence, disclosure, and human-approved narrative for one contribution.
_Avoid_: agent transcript, PR dump

**Project brief**:
A deterministic source manifest and a set of explicitly Skill/contributor-owned understanding sections for the selected repository and contribution context.
_Avoid_: AI-generated architecture summary, repository dump

**Candidate menu**:
A bounded set of possible contributions whose basis, duplicate-work evidence, value, scope, review cost, verifiability, risk, and recommended action are visible together.
_Avoid_: opportunity score, AI confidence ranking

**Evidence matrix**:
The candidate-menu fields used to compare work without collapsing maintainer demand, review cost, and verifiability into one numeric score.
_Avoid_: quality score, confidence score

**AI-assistance record**:
A structured record of where AI assisted, how the contributor verified the result, and where the resulting disclosure is placed.
_Avoid_: line-by-line authorship ledger

## Gates and policy

**Understanding gate**:
A checkpoint where the contributor explains the change and its reasoning in their own words; every contribution records a result, while the depth of questioning follows the contribution's risk profile. It is a learning and responsibility check, not cryptographic proof of authorship.
_Avoid_: anti-cheating gate, human detector

**Narrative gate**:
A checkpoint where the final title and Body are previewed and approved before public submission; independent human expression of motivation and trade-offs is additionally required when policy or risk makes it material.
_Avoid_: auto-generated PR description

**Review depth**:
The required depth of contribution checks, either `standard` or `heightened`; it is not a contribution-value or absolute-safety score. Risk signals and user escalation may raise it, but nothing may lower required checks, and hard-stops are evaluated separately.
_Avoid_: AI confidence score, quality score, safety rating

**Hard-stop**:
An independently blocking condition, such as a security issue, policy conflict, irreversible change, or unverifiable result, that prevents progression regardless of review depth.
_Avoid_: high-risk label, warning

**Result record**:
The durable outcome and evidence recorded for one contribution-flow node, including what was checked, what happened, and what remains unresolved.
_Avoid_: chat message, model assertion

**Orientation**:
The guided explanation of the approved contribution contract, final Diff, test evidence, and policy result that prepares a contributor for understanding assessment.
_Avoid_: answer key, solution dump

**Assessment**:
A set of new questions that checks whether the contributor can explain the oriented contribution in their own words. An Assessment is valid only for the exact materials it evaluated and expires when those materials materially change.
_Avoid_: quiz score, authorship proof

**Contribution policy**:
The project-specific rules governing acceptable contribution paths, required evidence, AI assistance, disclosure, and remote actions.
_Avoid_: generic AI policy, repository etiquette

**Disclosure location**:
The policy-approved public or repository record where AI assistance is disclosed, such as a PR Body, commit message, commit trailer, issue Body, or checklist.
_Avoid_: universal AI trailer

**Policy conflict**:
An unresolved incompatibility between project statements about how a contribution may be made or published; it is a safety condition that requires clarification rather than an implicit permission.
_Avoid_: policy disagreement, parser error

**Conservative mode**:
The default operating posture when contribution policy is missing or ambiguous: preserve human approval, require clear disclosure, and avoid assuming permission for risky actions.
_Avoid_: block everything mode, permissive fallback

**Remote write**:
An action that changes a hosted project's state, such as creating an issue, pull request, comment, branch, or review.
_Avoid_: publish, sync

**Operation ID**:
A stable identifier for one approved remote write attempt, used to connect the local contribution packet with remote idempotency checks and reconciliation evidence.
_Avoid_: request ID, retry token
