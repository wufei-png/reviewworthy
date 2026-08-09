"""Read-only checks over the public PR Evidence Summary."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .evidence import EvidenceSummaryError, extract_evidence_summary, summary_matches_repository
from .git import GitError, PR_DIFF_FIELDS, capture_pr_diff
from .policy import PolicyTreeError, inspect_policy_at_commit


ACTION_MODES = {"report", "evidence-enforce"}


def github_event_context() -> tuple[str | None, str | None, int | None, str | None, str | None, str | None]:
    """Read runner-owned pull-request identity and Body."""

    event_name = os.environ.get("GITHUB_EVENT_NAME") or None
    if event_name != "pull_request":
        return event_name, None, None, None, None, None
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return event_name, None, None, None, None, None
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return event_name, None, None, None, None, None
    if not isinstance(event, dict) or not isinstance(event.get("pull_request"), dict):
        return event_name, None, None, None, None, None
    repository = event.get("repository") if isinstance(event.get("repository"), dict) else {}
    pull_request = event["pull_request"]
    base = pull_request.get("base") if isinstance(pull_request.get("base"), dict) else {}
    head = pull_request.get("head") if isinstance(pull_request.get("head"), dict) else {}
    repository_slug = repository.get("full_name") if isinstance(repository.get("full_name"), str) else None
    raw_repository_id = repository.get("id")
    repository_id = raw_repository_id if isinstance(raw_repository_id, int) and not isinstance(raw_repository_id, bool) and raw_repository_id > 0 else None
    base_sha = base.get("sha") if isinstance(base.get("sha"), str) else None
    head_sha = head.get("sha") if isinstance(head.get("sha"), str) else None
    body = pull_request.get("body") if isinstance(pull_request.get("body"), str) else None
    return event_name, repository_slug, repository_id, base_sha, head_sha, body


def _finding(code: str, message: str, path: str) -> dict[str, str]:
    return {"code": code, "message": message, "path": path}


def _base_policy_projection(policy: dict[str, Any]) -> dict[str, Any]:
    document_claims: list[dict[str, Any]] = []
    for source in policy.get("sources", []):
        if not isinstance(source, dict) or source.get("kind") != "repository_document":
            continue
        claims = source.get("claims")
        if isinstance(claims, dict) and claims:
            document_claims.append({"source": source.get("path"), "claims": claims})
    structured = policy.get("structured_claims")
    return {
        "base_sha": policy.get("base_sha"),
        "machine_authority": structured if isinstance(structured, dict) else {},
        "document_advisory": document_claims,
        "conflicts": policy.get("conflicts", []),
        "ambiguities": policy.get("ambiguities", []),
    }


def _base_policy_blockers(policy: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if policy.get("conflicts"):
        blockers.append(_finding("base_policy_conflict", "Base-tree policy sources conflict.", "base_policy.conflicts"))
    if policy.get("ambiguities"):
        blockers.append(_finding("base_policy_ambiguity", "A base-tree policy document makes opposed explicit claims.", "base_policy.ambiguities"))

    document_prohibits_ai = any(
        isinstance(source, dict)
        and source.get("kind") == "repository_document"
        and isinstance(source.get("claims"), dict)
        and source["claims"].get("ai_assistance") == "prohibited"
        for source in policy.get("sources", [])
    )
    structured = policy.get("structured_claims") if isinstance(policy.get("structured_claims"), dict) else {}
    if document_prohibits_ai or structured.get("ai_assistance") == "prohibited":
        blockers.append(_finding("base_policy_ai_prohibited", "The base-tree policy explicitly prohibits AI-assisted contributions.", "base_policy.ai_assistance"))

    claims = summary.get("claims") if isinstance(summary.get("claims"), dict) else {}
    disclosure = claims.get("ai_disclosure") if isinstance(claims.get("ai_disclosure"), dict) else {}
    if structured.get("disclosure_required") is True and disclosure.get("claimed_present") is not True:
        blockers.append(_finding("base_policy_disclosure_required", "Structured base-tree policy requires an AI disclosure.", "claims.ai_disclosure.claimed_present"))
    return blockers


def check_evidence(
    body: str | None,
    *,
    root: Path,
    event_name: str | None,
    event_repository: str | None,
    event_repository_id: int | None,
    event_base_sha: str | None,
    event_head_sha: str | None,
    mode: str = "report",
) -> dict[str, Any]:
    """Check current public evidence without reading a private Packet."""

    if mode not in ACTION_MODES:
        raise ValueError(f"mode must be one of {sorted(ACTION_MODES)}")
    enforce = mode == "evidence-enforce"
    violations: list[dict[str, str]] = []
    unknowns: list[str] = []
    verified_facts: dict[str, Any] = {}

    try:
        summary = extract_evidence_summary(body or "")
    except EvidenceSummaryError as exc:
        if enforce:
            violations.append(_finding("evidence_summary_required", str(exc), "pull_request.body"))
        else:
            unknowns.append(str(exc))
        return {
            "conclusion": "failure" if violations else "success",
            "mode": mode,
            "checked": False,
            "violations": violations,
            "unknowns": unknowns,
            "verified_facts": verified_facts,
            "contributor_claims": {},
        }

    base_policy: dict[str, Any] = {
        "base_sha": event_base_sha,
        "machine_authority": {},
        "document_advisory": [],
        "conflicts": [],
        "ambiguities": [],
    }
    if event_base_sha:
        try:
            inspected_policy = inspect_policy_at_commit(root, event_base_sha)
            base_policy = _base_policy_projection(inspected_policy)
            policy_blockers = _base_policy_blockers(inspected_policy, summary)
            if enforce:
                violations.extend(policy_blockers)
            elif policy_blockers:
                unknowns.extend(item["message"] for item in policy_blockers)
        except PolicyTreeError as exc:
            if enforce:
                violations.append(_finding("base_policy_unavailable", str(exc), "event.pull_request.base.sha"))
            else:
                unknowns.append(f"Base-tree policy unavailable: {exc}")
    elif enforce:
        violations.append(_finding("base_policy_unavailable", "Runner event does not provide a base SHA.", "event.pull_request.base.sha"))

    if event_name != "pull_request":
        violations.append(_finding("pull_request_context_required", "Evidence checks require a pull_request event.", "event_name"))
    if not event_repository or event_repository_id is None:
        violations.append(_finding("repository_context_required", "Runner-owned repository identity is incomplete.", "event.repository"))
    elif not summary_matches_repository(summary, event_repository, event_repository_id):
        violations.append(_finding("repository_identity_mismatch", "Evidence Summary repository identity differs from the runner event.", "repository"))
    else:
        verified_facts["repository"] = {"slug": event_repository, "repository_id": event_repository_id}

    current_diff: dict[str, Any] | None = None
    if event_base_sha and event_head_sha:
        try:
            current_diff = capture_pr_diff(root, event_base_sha, event_head_sha)
        except GitError as exc:
            violations.append(_finding("current_diff_unavailable", str(exc), "diff"))
    else:
        violations.append(_finding("pull_request_commits_required", "Runner event must provide base and head SHAs.", "event.pull_request"))
    declared_diff = summary.get("diff") if isinstance(summary.get("diff"), dict) else {}
    if current_diff is not None:
        for field in PR_DIFF_FIELDS:
            if declared_diff.get(field) != current_diff.get(field):
                violations.append(
                    _finding(
                        f"current_diff_{field}_mismatch",
                        f"Recomputed pull-request Diff {field} differs from the public Evidence Summary.",
                        f"diff.{field}",
                    )
                )
        if event_base_sha and current_diff.get("base_tip_sha") != event_base_sha:
            violations.append(_finding("current_base_tip_sha_mismatch", "Recomputed base tip differs from the runner event.", "diff.base_tip_sha"))
        if event_head_sha and current_diff.get("head_sha") != event_head_sha:
            violations.append(_finding("current_head_sha_mismatch", "Recomputed head differs from the runner event.", "diff.head_sha"))
        if not any(item["code"].startswith("current_diff_") for item in violations):
            verified_facts["diff"] = {field: current_diff.get(field) for field in PR_DIFF_FIELDS}

    return {
        "conclusion": "failure" if violations else "success",
        "mode": mode,
        "checked": True,
        "violations": violations,
        "unknowns": unknowns,
        "verified_facts": verified_facts,
        "contributor_claims": summary.get("claims", {}),
        "base_policy": base_policy,
        "summary": summary,
    }
