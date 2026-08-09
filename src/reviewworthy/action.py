"""Read-only checks over the public PR Evidence Summary."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .evidence import EvidenceSummaryError, extract_evidence_summary, summary_matches_repository
from .git import GitError, PR_DIFF_FIELDS, capture_pr_diff


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
        "summary": summary,
    }
