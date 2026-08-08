"""Read-only, deterministic checks suitable for a GitHub Action."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .git import GitError, PR_DIFF_FIELDS, capture_pr_diff
from .packet import deterministic_evidence_checks, policy_violations, validate_packet
from .policy import CLAIM_KEYS
from .repository import repository_slugs_match
from .util import read_json


ACTION_MODES = {"report", "enforce"}
CURRENT_DIFF_FIELDS = PR_DIFF_FIELDS


def github_event_context() -> tuple[str | None, str | None, int | None, str | None, str | None]:
    """Read runner-owned repository and pull-request identity."""

    event_name = os.environ.get("GITHUB_EVENT_NAME") or None
    if event_name != "pull_request":
        return event_name, None, None, None, None
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return event_name, None, None, None, None
    try:
        event = read_json(Path(event_path))
    except (OSError, ValueError):
        return event_name, None, None, None, None
    if not isinstance(event, dict) or not isinstance(event.get("pull_request"), dict):
        return event_name, None, None, None, None
    repository = event.get("repository") if isinstance(event.get("repository"), dict) else {}
    repository_slug = repository.get("full_name") if isinstance(repository.get("full_name"), str) else None
    raw_repository_id = repository.get("id")
    repository_id = raw_repository_id if isinstance(raw_repository_id, int) and not isinstance(raw_repository_id, bool) and raw_repository_id > 0 else None
    pull_request = event["pull_request"]
    base = pull_request.get("base") if isinstance(pull_request.get("base"), dict) else {}
    head = pull_request.get("head") if isinstance(pull_request.get("head"), dict) else {}
    base_sha = base.get("sha") if isinstance(base.get("sha"), str) else None
    head_sha = head.get("sha") if isinstance(head.get("sha"), str) else None
    return event_name, repository_slug, repository_id, base_sha, head_sha


def _complete_diff(value: Any) -> bool:
    return isinstance(value, dict) and all(field in value for field in CURRENT_DIFF_FIELDS)


def _usable_verification_receipts(packet: dict[str, Any]) -> list[dict[str, Any]]:
    verification = packet.get("verification", {})
    receipts = verification.get("receipts", []) if isinstance(verification, dict) else []
    return [
        receipt
        for receipt in receipts
        if isinstance(receipt, dict)
        and receipt.get("provenance") == "cli_executed"
        and receipt.get("exit_code") == 0
        and receipt.get("status") == "valid"
        and isinstance(receipt.get("head_sha"), str)
        and receipt.get("head_sha")
        and receipt.get("head_sha_before") == receipt.get("head_sha") == receipt.get("head_sha_after")
        and receipt.get("worktree_clean_before") is True
        and receipt.get("worktree_clean_after") is True
    ]


def _append_required_action_evidence(
    *,
    enforce: bool,
    violations: list[dict[str, str]],
    unknowns: list[str],
    code: str,
    message: str,
    path: str,
) -> None:
    if enforce:
        violations.append({"code": code, "message": message, "path": path})
    else:
        unknowns.append(message)


def check_packet(
    path: Path,
    changed_files: list[str] | None = None,
    *,
    root: Path | None = None,
    current_diff: dict[str, Any] | None = None,
    current_diff_available: bool | None = None,
    event_name: str | None = None,
    event_repository: str | None = None,
    event_repository_id: int | None = None,
    event_base_sha: str | None = None,
    event_head_sha: str | None = None,
    mode: str = "report",
    require_packet: bool = False,
    fail_on_unknown: bool = False,
    require_current_diff: bool = False,
) -> dict[str, Any]:
    """Check a packet in report mode, or opt into explicit enforcement.

    Report mode preserves the original read-only, non-blocking behavior for
    missing packets and unknown evidence. Enforce mode turns all three
    explicit requirements on; callers may also opt into individual
    requirements while remaining in report mode.
    """

    if mode not in ACTION_MODES:
        raise ValueError(f"mode must be one of {sorted(ACTION_MODES)}")
    enforce = mode == "enforce"
    require_packet = require_packet or enforce
    fail_on_unknown = fail_on_unknown or enforce
    require_current_diff = require_current_diff or enforce
    has_current_diff = changed_files is not None if current_diff_available is None else current_diff_available
    if event_name == "pull_request" and root is not None and event_base_sha and event_head_sha:
        try:
            captured_diff = capture_pr_diff(root, event_base_sha, event_head_sha)
        except GitError:
            captured_diff = None
        if enforce or captured_diff is not None:
            current_diff = captured_diff
    elif enforce:
        current_diff = None
    has_complete_current_diff = _complete_diff(current_diff)
    has_current_diff = has_current_diff or has_complete_current_diff
    if has_complete_current_diff:
        evidence_files = current_diff["changed_files"] if isinstance(current_diff.get("changed_files"), list) else []
    else:
        evidence_files = changed_files if current_diff_available is not False else []

    requirements = {
        "require_packet": require_packet,
        "fail_on_unknown": fail_on_unknown,
        "require_current_diff": require_current_diff,
    }
    if not path.is_file():
        violations = []
        if require_packet:
            violations.append({"code": "packet_required", "message": f"Contribution packet is required: {path}", "path": str(path)})
        return {
            "conclusion": "failure" if violations else "success",
            "violations": violations,
            "unknowns": [f"Contribution packet not found: {path}"],
            "checked": False,
            "mode": mode,
            "requirements": requirements,
        }

    try:
        packet = read_json(path)
    except (OSError, ValueError) as exc:
        return {
            "conclusion": "failure",
            "violations": [{"code": "invalid_json", "message": str(exc)}],
            "unknowns": [],
            "checked": True,
            "mode": mode,
            "requirements": requirements,
        }

    if not isinstance(packet, dict):
        return {
            "conclusion": "failure",
            "violations": [{"code": "invalid_packet", "message": "Contribution packet must be a JSON object."}],
            "unknowns": [],
            "checked": True,
            "mode": mode,
            "requirements": requirements,
        }

    validation = validate_packet(packet)
    violations = list(validation["errors"])
    unknowns: list[str] = []

    policy = packet.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    claims = policy.get("authoritative_claims", {})
    policy_complete = isinstance(claims, dict) and all(key in claims and claims[key] is not None for key in CLAIM_KEYS)
    if not policy:
        unknowns.append("Policy result is absent; Action does not infer permission.")
    elif not policy.get("authoritative_claims") or policy.get("posture") == "conservative":
        unknowns.append("Policy contains unknown claims; Action reports this without blocking by default.")
    else:
        missing_claims = sorted(key for key in CLAIM_KEYS if not isinstance(claims, dict) or claims.get(key) is None)
        if missing_claims:
            unknowns.append(f"Policy claims are incomplete; Action cannot infer missing claims: {missing_claims}.")

    violations.extend(policy_violations(packet, enforce_disclosure=policy.get("posture") == "explicit" and policy_complete))
    evidence_violations, evidence_unknowns = deterministic_evidence_checks(packet, evidence_files, strict=fail_on_unknown)
    violations.extend(evidence_violations)
    unknowns.extend(evidence_unknowns)

    if enforce and not has_complete_current_diff:
        violations.append(
            {
                "code": "current_diff_required",
                "message": "Enforce mode requires a complete current pull-request Diff receipt.",
                "path": "current_diff",
            }
        )
    else:
        if event_name == "pull_request" and not has_complete_current_diff:
            unknowns.append("The complete current pull-request Diff could not be recomputed from local commit objects.")
        if require_current_diff and not has_current_diff:
            violations.append(
                {
                    "code": "current_diff_required",
                    "message": "Current changed-file evidence is required; packet-declared files are not sufficient.",
                    "path": "diff.changed_files",
                }
            )
    if has_complete_current_diff:
        packet_diff = packet.get("diff", {})
        if not isinstance(packet_diff, dict):
            packet_diff = {}
        for field in CURRENT_DIFF_FIELDS:
            if packet_diff.get(field) != current_diff.get(field):
                violations.append(
                    {
                        "code": f"current_diff_{field}_mismatch",
                        "message": f"Current pull-request Diff {field} differs from packet.diff.{field}.",
                        "path": f"diff.{field}",
                    }
                )

    if enforce or event_name or event_repository or event_repository_id or event_base_sha or event_head_sha:
        if event_name != "pull_request":
            _append_required_action_evidence(
                enforce=enforce,
                violations=violations,
                unknowns=unknowns,
                code="pull_request_context_required",
                message="Enforce mode requires a real pull_request event context.",
                path="event_name",
            )
        if event_name == "pull_request" and not event_base_sha:
            _append_required_action_evidence(
                enforce=enforce,
                violations=violations,
                unknowns=unknowns,
                code="pull_request_base_required",
                message="The current pull_request base SHA is unavailable.",
                path="event_base_sha",
            )
        if event_name == "pull_request" and not event_head_sha:
            _append_required_action_evidence(
                enforce=enforce,
                violations=violations,
                unknowns=unknowns,
                code="pull_request_head_required",
                message="The current pull_request head SHA is unavailable.",
                path="event_head_sha",
            )
        repository = packet.get("repository") if isinstance(packet.get("repository"), dict) else {}
        packet_owner = repository.get("owner") if isinstance(repository.get("owner"), str) else None
        packet_name = repository.get("name") if isinstance(repository.get("name"), str) else None
        packet_repository = f"{packet_owner}/{packet_name}" if packet_owner and packet_name else None
        packet_repository_id = repository.get("repository_id")
        if event_name == "pull_request" and not event_repository:
            _append_required_action_evidence(
                enforce=enforce,
                violations=violations,
                unknowns=unknowns,
                code="repository_context_required",
                message="The runner-owned repository slug is unavailable.",
                path="event_repository",
            )
        elif event_name == "pull_request" and packet_repository and not repository_slugs_match(packet_repository, event_repository):
            violations.append({
                "code": "repository_slug_mismatch",
                "message": "The packet repository slug does not match the runner-owned repository slug.",
                "path": "repository",
            })
        if event_name == "pull_request" and event_repository_id is None:
            _append_required_action_evidence(
                enforce=enforce,
                violations=violations,
                unknowns=unknowns,
                code="repository_id_context_required",
                message="The runner-owned numeric repository ID is unavailable.",
                path="event_repository_id",
            )
        if event_name == "pull_request" and packet_repository_id is None:
            _append_required_action_evidence(
                enforce=enforce,
                violations=violations,
                unknowns=unknowns,
                code="packet_repository_id_required",
                message="The packet numeric repository ID is unavailable.",
                path="repository.repository_id",
            )
        elif event_name == "pull_request" and event_repository_id is not None and packet_repository_id != event_repository_id:
            violations.append({
                "code": "repository_id_mismatch",
                "message": "The packet numeric repository ID does not match the runner-owned repository ID.",
                "path": "repository.repository_id",
            })
        if has_complete_current_diff and event_name == "pull_request":
            if event_base_sha and current_diff.get("base_tip_sha") != event_base_sha:
                violations.append(
                    {
                        "code": "current_base_tip_sha_mismatch",
                        "message": "The recomputed Diff base tip SHA does not match the current pull_request base SHA.",
                        "path": "current_diff.base_tip_sha",
                    }
                )
            if event_head_sha and current_diff.get("head_sha") != event_head_sha:
                violations.append(
                    {
                        "code": "current_head_sha_mismatch",
                        "message": "The recomputed Diff head SHA does not match the current pull_request head SHA.",
                        "path": "current_diff.head_sha",
                    }
                )

        receipts = _usable_verification_receipts(packet)
        if not receipts:
            _append_required_action_evidence(
                enforce=enforce,
                violations=violations,
                unknowns=unknowns,
                code="verification_receipt_required",
                message="A successful clean-worktree CLI verification receipt is required.",
                path="verification.receipts",
            )
        elif event_name == "pull_request" and event_head_sha and not any(receipt["head_sha"] == event_head_sha for receipt in receipts):
            violations.append(
                {
                    "code": "verification_head_mismatch",
                    "message": "No successful verification receipt is bound to the current pull_request head SHA.",
                    "path": "verification.receipts",
                }
            )
    if fail_on_unknown:
        for message in unknowns:
            code = "unknown_policy" if message.startswith("Policy") else "unknown_evidence"
            path_value = "policy" if code == "unknown_policy" else "diff"
            violations.append({"code": code, "message": message, "path": path_value})

    return {
        "conclusion": "failure" if violations else "success",
        "violations": violations,
        "unknowns": unknowns,
        "checked": True,
        "mode": mode,
        "requirements": requirements,
    }
