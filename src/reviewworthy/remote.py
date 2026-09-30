"""Shared live inspection of saved operations; never creates remote objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .github import (
    GhClient, GhError, MarkerAmbiguityError, RemoteOperation,
    _canonical_operation_remote, _write_operation_record,
)
from .util import utc_now


def inspect_operation(
    client: GhClient, operation: RemoteOperation, record: dict[str, Any],
) -> dict[str, Any]:
    """Check immutable repository identity, a known object, and marker ambiguity."""

    result: dict[str, Any] = {"outcome": "needs_reconciliation", "diagnostics": []}

    def diagnostic(code: str, message: str) -> None:
        result["diagnostics"].append({"code": code, "message": message, "path": "operation"})

    client.verify_repository_identity(operation.repo, operation.repository_id)
    remote = record.get("pr_url") or record.get("remote") or record.get("known_remote")
    live = None
    if remote:
        result["remote"] = remote
        try:
            live = client.read_operation_object(operation, remote)
        except GhError as exc:
            diagnostic("remote_object_unavailable", str(exc))
    try:
        matches = client.find_existing(operation)
    except MarkerAmbiguityError as exc:
        matches = exc.matches
    except GhError as exc:
        matches = None
        diagnostic("remote_marker_search_unavailable", str(exc))
    if matches is not None:
        urls = sorted({_canonical_operation_remote(operation, item.get("url") or item.get("html_url")) for item in matches})
        result["matches"] = urls
        if len(urls) > 1 or (remote and any(url != remote for url in urls)):
            result["matches"] = sorted(set(urls + ([remote] if remote else [])))
            diagnostic("remote_marker_ambiguous", "Multiple objects are visible; inspect every URL before recovery.")
        elif not remote and urls:
            remote = urls[0]
            result["remote"] = remote
            try:
                live = client.read_operation_object(operation, remote)
            except GhError as exc:
                diagnostic("remote_object_unavailable", str(exc))
        elif not remote:
            diagnostic("remote_marker_not_found", "No object is visible. Preserve pending state; manually inspect before an explicit uncertain retry.")
    if live is not None:
        body = live.get("body")
        if not isinstance(body, str) or operation.marker not in body:
            diagnostic("remote_marker_missing", "The known object lost its operation marker; inspect it manually.")
        if live.get("title") != operation.title or body != operation.body:
            diagnostic("remote_payload_drift", "The public title or Body differs from the saved operation; inspect without rewriting it.")
        if operation.kind == "pull_request":
            head = live.get("head")
            sha = head.get("sha") if isinstance(head, dict) else None
            result["remote_head_sha"] = sha
            if not sha:
                diagnostic("remote_pr_head_unavailable", "The PR response has no head SHA.")
            elif sha != operation.head_sha:
                diagnostic("remote_pr_head_mismatch", "The PR head differs from the original operation head.")
            base = live.get("base")
            if not isinstance(base, dict) or base.get("ref") != operation.base or live.get("draft") != operation.draft:
                diagnostic("remote_payload_drift", "The PR base or draft state differs from the original operation.")
    if remote and live is not None and matches is not None and not result["diagnostics"]:
        result["outcome"] = "already_exists"
    return result


def record_inspection(path: Path, record: dict[str, Any], inspection: dict[str, Any]) -> None:
    """Keep known URLs even when live inspection or later local repair fails."""

    updated = dict(record)
    if inspection.get("remote"):
        updated["known_remote"] = inspection["remote"]
    updated["inspection"] = {**inspection, "recorded_at": utc_now()}
    _write_operation_record(path, updated, "Could not persist remote inspection; preserve the known URL and reconcile again")
