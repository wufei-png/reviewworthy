"""Contribution Packet validation and understanding-material freshness."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
import re
from typing import Any

from .candidate import DUPLICATE_BLOCKING_DISPOSITIONS, DUPLICATE_DISPOSITIONS, RECOMMENDATIONS
from .contract import CONTRACT_FIELDS, CONTRACT_VERSION, contract_snapshot
from .disclosure import ASSISTANCE_LEVELS, DISCLOSURE_STAGES, disclosure_errors
from .git import FINGERPRINT_ALGORITHM, PR_DIFF_FIELDS, VERIFICATION_PLAN_VERSION, VERIFICATION_RECEIPT_VERSION, verification_plan_digest
from .repository import parse_public_record, parse_repository_slug, repository_slugs_match, validate_repository_identity
from .signal import SIGNAL_VERSION, signal_readiness_blockers, skeleton_signal, validate_basis_signal
from .understanding import validate_understanding
from .util import has_normalized_label, normalize_label, sha256_json


REQUIRED_NODES = (
    "policy_check",
    "contribution_basis",
    "contribution_contract",
    "implementation",
    "verification",
    "ownership",
    "narrative",
)
ALLOWED_STATUSES = {"passed", "failed", "blocked", "unknown", "not_run"}
PACKET_VERSION = "0.3"
CONTRIBUTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PR_DIFF_STRING_FIELDS = (
    "base_tip_sha",
    "merge_base_sha",
    "head_sha",
    "subject_digest",
    "fingerprint_algorithm",
)


def packet_format_errors(packet: Any) -> list[dict[str, str]]:
    """Return hard current-format boundary errors without interpreting content."""

    if not isinstance(packet, dict):
        return [{"code": "invalid_packet", "message": "Contribution Packet must be a JSON object", "path": "packet"}]
    if packet.get("packet_version") != PACKET_VERSION:
        return [{"code": "invalid_packet_version", "message": f"packet_version must be {PACKET_VERSION}", "path": "packet_version"}]
    basis = packet.get("basis")
    if isinstance(basis, dict) and "signal" in basis:
        signal = basis.get("signal")
        if not isinstance(signal, dict) or signal.get("signal_version") != SIGNAL_VERSION:
            return [{"code": "invalid_signal_version", "message": f"Embedded Signal must be {SIGNAL_VERSION}", "path": "basis.signal.signal_version"}]
    verification = packet.get("verification")
    receipts = verification.get("receipts") if isinstance(verification, dict) else None
    if isinstance(verification, dict) and "receipts" in verification and not isinstance(receipts, list):
        return [{"code": "invalid_receipts", "message": "verification.receipts must be a current list", "path": "verification.receipts"}]
    if isinstance(receipts, list):
        for index, receipt in enumerate(receipts):
            if not isinstance(receipt, dict) or receipt.get("receipt_version") != VERIFICATION_RECEIPT_VERSION:
                return [{
                    "code": "invalid_receipt_version",
                    "message": f"Embedded verification receipts must be {VERIFICATION_RECEIPT_VERSION}",
                    "path": f"verification.receipts[{index}].receipt_version",
                }]
    return []


def require_current_packet(packet: Any) -> dict[str, Any]:
    """Reject non-current Packet, Signal, or receipt formats before consumption."""

    errors = packet_format_errors(packet)
    if errors:
        raise ValueError(
            f"Only Packet {PACKET_VERSION} with current Signal and receipt formats is supported; "
            f"older formats are not read or migrated ({errors[0]['path']})"
        )
    return packet


def _is_repository_relative_path(value: str) -> bool:
    """Return whether a public path is relative under POSIX and Windows rules."""

    posix_path = Path(value)
    windows_path = PureWindowsPath(value)
    return not (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    )


def require_contribution_id(value: Any) -> str:
    """Return a path-safe contribution identifier or reject it."""

    if not isinstance(value, str) or CONTRIBUTION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("contribution_id must be 1-128 ASCII letters, digits, dots, underscores, or hyphens and start with a letter or digit")
    return value


def semantic_snapshot(packet: dict[str, Any]) -> str:
    """Hash semantic readiness inputs while excluding timestamps and audit output."""

    def without_audit_timestamps(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: without_audit_timestamps(item)
                for key, item in value.items()
                if key not in {"verified_at", "captured_at", "started_at", "finished_at"}
            }
        if isinstance(value, list):
            return [without_audit_timestamps(item) for item in value]
        return value

    verification = packet.get("verification") if isinstance(packet.get("verification"), dict) else {}
    receipts = verification.get("receipts", []) if isinstance(verification.get("receipts", []), list) else []
    semantic_receipts = sorted([
        {
            key: receipt.get(key)
            for key in ("receipt_version", "check_id", "plan_digest", "subject_digest", "command_outcome", "integrity_status")
        }
        for receipt in receipts
        if isinstance(receipt, dict)
    ], key=lambda item: str(item.get("check_id", "")))
    diff = packet.get("diff") if isinstance(packet.get("diff"), dict) else {}
    policy = packet.get("policy") if isinstance(packet.get("policy"), dict) else {}

    return sha256_json(
        {
            "entry": packet.get("entry", {}),
            "basis": without_audit_timestamps(packet.get("basis", {})),
            "candidate_selection": packet.get("candidate_selection", {}),
            "contract": packet.get("contract", {}),
            "diff": {key: diff.get(key) for key in PR_DIFF_FIELDS},
            "verification": {
                "plan": verification.get("plan", {}),
                "plan_digest": verification.get("plan_digest"),
                "receipts": semantic_receipts,
            },
            "policy": {
                "authoritative_claims": policy.get("authoritative_claims", {}),
                "conflicts": policy.get("conflicts", []),
                "ambiguities": policy.get("ambiguities", []),
                "posture": policy.get("posture"),
            },
            "review": packet.get("review", {}),
            "ownership": packet.get("ownership", {}),
        }
    )


def result_record(
    node: str,
    status: str,
    evidence: list[str] | None = None,
    details: dict[str, Any] | None = None,
    semantic_snapshot_value: str | None = None,
) -> dict[str, Any]:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported result status: {status}")
    record: dict[str, Any] = {
        "node": node,
        "status": status,
        "evidence": evidence or [],
        "details": details or {},
    }
    if semantic_snapshot_value:
        record["semantic_snapshot"] = semantic_snapshot_value
    return record


def skeleton_packet(contribution_id: str, mode: str, repository: str | None = None) -> dict[str, Any]:
    """Create an explicit, incomplete packet for a new contribution."""

    require_contribution_id(contribution_id)
    if mode not in {"issue-backed", "discovery"}:
        raise ValueError("mode must be issue-backed or discovery")
    repository_value: dict[str, Any] = {
        "provider": "github",
        "host": "github.com",
        "owner": "",
        "name": "",
        "repository_id": None,
        "default_branch": "main",
        "base_sha": "",
    }
    if repository:
        owner, name = parse_repository_slug(repository)
        repository_value.update({"owner": owner, "name": name})
    packet: dict[str, Any] = {
        "packet_version": PACKET_VERSION,
        "contribution_id": contribution_id,
        "repository": repository_value,
        "entry": {"mode": mode, "source": ""},
        "basis": {"kind": "issue" if mode == "issue-backed" else "discovery-evidence", "references": [], "evidence": []},
        "contract": {
            "contract_version": "0.1",
            "contribution_id": contribution_id,
            "problem": "",
            "non_goals": [],
            "scope": {"files": []},
            "invariants": [],
            "design": "",
            "alternatives": [],
            "validation_plan": [],
            "risks": [],
            "success_criteria": [],
            "max_diff_lines": 400,
            "approval": {"status": "not_run", "human_confirmed": False},
        },
        "policy": {"authoritative_claims": {}, "conflicts": [], "posture": "conservative"},
        "review": {"profile": "standard", "signals": [], "hard_stops": []},
        "ai_assistance": {
            "used": True,
            "stages": [],
            "disclosure": {"text": "", "locations": [], "human_confirmed": False},
        },
        "diff": {
            "comparison": "merge_base",
            "base_tip_sha": "",
            "merge_base_sha": "",
            "head_sha": "",
            "subject_digest": "",
            "fingerprint_algorithm": "git-raw-content-v1",
            "changed_files": [],
            "additions": 0,
            "deletions": 0,
        },
        "verification": {
            "plan": {"plan_version": VERIFICATION_PLAN_VERSION, "checks": []},
            "plan_digest": "",
            "receipts": [],
        },
        "ownership": {"status": "not_run", "problem": "", "scope": "", "verification": "", "risks": []},
        "snapshots": {},
        "results": [result_record(node, "not_run") for node in REQUIRED_NODES],
        "understanding": {
            "orientation": {"status": "not_run", "summary": "", "topics": [], "evidence": [], "rubric": {"covered": [], "evidence": {}}, "semantic_snapshot": ""},
            "assessment": {"status": "not_run", "questions": [], "answers": [], "evidence": [], "rubric": {"covered": [], "evidence": {}}, "semantic_snapshot": ""},
        },
        "narrative": {
            "title": "",
            "body": "",
            "final_preview_confirmed": False,
            "human_expression_required": False,
            "human_expression": "",
        },
    }
    if mode == "discovery":
        packet["basis"]["signal"] = skeleton_signal("local_evidence", "reproducible_evidence", "local:unpublished")
    packet["verification"]["plan_digest"] = verification_plan_digest(packet["verification"]["plan"])
    packet["snapshots"]["semantic"] = semantic_snapshot(packet)
    packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
    packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
    return packet


def _error(errors: list[dict[str, str]], code: str, message: str, path: str) -> None:
    errors.append({"code": code, "message": message, "path": path})


def _validate_packet_object(packet: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    required_top = (
        "packet_version",
        "contribution_id",
        "repository",
        "entry",
        "basis",
        "contract",
        "policy",
        "review",
        "ai_assistance",
        "diff",
        "verification",
        "ownership",
        "snapshots",
        "results",
        "understanding",
        "narrative",
    )
    allowed_top = {*required_top, "candidate_selection"}
    for key in sorted(set(packet) - allowed_top):
        _error(errors, "unknown_packet_field", f"{key} is not part of Packet {PACKET_VERSION}", key)
    for key in required_top:
        if key not in packet:
            _error(errors, "missing_field", f"Required field is missing: {key}", key)

    if packet.get("packet_version") != PACKET_VERSION:
        _error(errors, "invalid_packet_version", f"packet_version must be {PACKET_VERSION}", "packet_version")
    try:
        require_contribution_id(packet.get("contribution_id"))
    except ValueError as exc:
        _error(errors, "invalid_contribution_id", str(exc), "contribution_id")

    errors.extend(validate_repository_identity(packet.get("repository")))

    entry = packet.get("entry", {})
    if not isinstance(entry, dict) or entry.get("mode") not in {"issue-backed", "discovery"}:
        _error(errors, "invalid_entry", "entry.mode must be issue-backed or discovery", "entry.mode")

    basis = packet.get("basis", {})
    if not isinstance(basis, dict) or basis.get("kind") not in {"issue", "signal", "discovery-evidence"}:
        _error(errors, "invalid_basis", "basis.kind must be issue, signal, or discovery-evidence", "basis.kind")
    elif basis.get("kind") == "issue" and not basis.get("references") and not basis.get("evidence"):
        _error(errors, "empty_basis", "A contribution basis needs references or reproducible evidence", "basis")
    if isinstance(basis, dict):
        errors.extend(validate_basis_signal(basis, entry.get("mode") if isinstance(entry, dict) else ""))

    contract = packet.get("contract", {})
    if not isinstance(contract, dict):
        _error(errors, "invalid_contract", "contract must be an object", "contract")
    else:
        if contract.get("contract_version") != CONTRACT_VERSION:
            _error(errors, "unsupported_contract_version", "contract_version must be 0.1", "contract.contract_version")
        if not isinstance(contract.get("contribution_id"), str) or not contract.get("contribution_id", "").strip():
            _error(errors, "missing_contract_contribution_id", "contract.contribution_id is required", "contract.contribution_id")
        elif contract.get("contribution_id") != packet.get("contribution_id"):
            _error(errors, "contribution_id_mismatch", "contract.contribution_id must match packet.contribution_id", "contract.contribution_id")
        for key in CONTRACT_FIELDS:
            if key not in contract:
                _error(errors, "missing_contract_field", f"Contribution contract field is missing: {key}", f"contract.{key}")
        for list_key in ("non_goals", "invariants", "alternatives", "validation_plan", "risks", "success_criteria"):
            if list_key in contract and not isinstance(contract[list_key], list):
                _error(errors, "invalid_contract_list", f"contract.{list_key} must be a list", f"contract.{list_key}")
        if not isinstance(contract.get("max_diff_lines"), int) or isinstance(contract.get("max_diff_lines"), bool) or contract.get("max_diff_lines", 0) <= 0:
            _error(errors, "invalid_diff_budget", "contract.max_diff_lines must be a positive integer", "contract.max_diff_lines")
        approval = contract.get("approval")
        if approval is not None:
            if not isinstance(approval, dict):
                _error(errors, "invalid_approval", "contract.approval must be an object", "contract.approval")
            else:
                if approval.get("status") not in {"not_run", "approved", "rejected"}:
                    _error(errors, "invalid_approval_status", "contract.approval.status must be not_run, approved, or rejected", "contract.approval.status")
                if not isinstance(approval.get("human_confirmed"), bool):
                    _error(errors, "invalid_approval_confirmation", "contract.approval.human_confirmed must be boolean", "contract.approval.human_confirmed")
                if approval.get("status") == "approved":
                    if not isinstance(approval.get("contract_sha256"), str) or not approval.get("contract_sha256", "").strip():
                        _error(errors, "missing_approval_snapshot", "An approved contract needs contract_sha256", "contract.approval.contract_sha256")
                    elif approval.get("contract_sha256") != contract_snapshot(contract):
                        _error(errors, "stale_contract_approval", "Contract approval does not match the current contract fields", "contract.approval.contract_sha256")
        scope = contract.get("scope")
        if isinstance(scope, dict):
            for scope_key in ("files", "modules"):
                scope_value = scope.get(scope_key, [])
                if not isinstance(scope_value, list):
                    _error(errors, "invalid_scope", f"contract.scope.{scope_key} must be a list", f"contract.scope.{scope_key}")
                elif not all(isinstance(item, str) for item in scope_value):
                    _error(errors, "invalid_scope_item", f"contract.scope.{scope_key} items must be strings", f"contract.scope.{scope_key}")
            if not scope.get("files") and not scope.get("modules"):
                _error(errors, "empty_scope", "At least one file or module must be bounded", "contract.scope")

    review = packet.get("review", {})
    if not isinstance(review, dict) or review.get("profile") not in {"standard", "heightened", "learning"}:
        _error(errors, "invalid_review_profile", "review.profile must be standard, heightened, or learning", "review.profile")
    if isinstance(review, dict) and not isinstance(review.get("hard_stops", []), list):
        _error(errors, "invalid_hard_stops", "review.hard_stops must be a list", "review.hard_stops")
    if isinstance(review, dict):
        for key in sorted(set(review) - {"profile", "signals", "hard_stops"}):
            _error(errors, "unknown_review_field", f"review.{key} is not part of Packet {PACKET_VERSION}", f"review.{key}")
        if not isinstance(review.get("signals", []), list):
            _error(errors, "invalid_review_signals", "review.signals must be a list", "review.signals")
        elif review.get("signals") and review.get("profile") == "standard":
            _error(errors, "review_profile_too_low", "Risk signals require a full review profile", "review.profile")

    ai_assistance = packet.get("ai_assistance", {})
    if not isinstance(ai_assistance, dict):
        _error(errors, "invalid_ai_assistance", "ai_assistance must be an object", "ai_assistance")
    else:
        if not isinstance(ai_assistance.get("used"), bool):
            _error(errors, "invalid_ai_used", "ai_assistance.used must be boolean", "ai_assistance.used")
        stages = ai_assistance.get("stages", [])
        if not isinstance(stages, list):
            _error(errors, "invalid_ai_stages", "ai_assistance.stages must be a list", "ai_assistance.stages")
        else:
            if ai_assistance.get("used") is False and stages:
                _error(errors, "ai_usage_record_conflict", "ai_assistance.used=false cannot include AI-assistance stages", "ai_assistance.stages")
            for index, stage in enumerate(stages):
                if not isinstance(stage, dict):
                    _error(errors, "invalid_ai_stage", "Each AI-assistance stage must be an object", f"ai_assistance.stages[{index}]")
                    continue
                if stage.get("name") not in DISCLOSURE_STAGES:
                    _error(errors, "invalid_ai_stage_name", "AI-assistance stage name is not supported", f"ai_assistance.stages[{index}].name")
                if stage.get("level") not in ASSISTANCE_LEVELS:
                    _error(errors, "invalid_ai_stage_level", "AI-assistance stage level is not supported", f"ai_assistance.stages[{index}].level")
                if not isinstance(stage.get("human_verified"), bool):
                    _error(errors, "invalid_ai_stage_verification", "AI-assistance stage human_verified must be boolean", f"ai_assistance.stages[{index}].human_verified")
        if "disclosure" not in ai_assistance:
            _error(errors, "missing_ai_disclosure_record", "ai_assistance.disclosure is required", "ai_assistance.disclosure")
        else:
            disclosure = ai_assistance.get("disclosure")
            if not isinstance(disclosure, dict):
                _error(errors, "invalid_ai_disclosure", "ai_assistance.disclosure must be an object", "ai_assistance.disclosure")
            else:
                if not isinstance(disclosure.get("text"), str):
                    _error(errors, "invalid_ai_disclosure_text", "ai_assistance.disclosure.text must be a string", "ai_assistance.disclosure.text")
                if not isinstance(disclosure.get("locations"), list):
                    _error(errors, "invalid_ai_disclosure_locations", "ai_assistance.disclosure.locations must be a list", "ai_assistance.disclosure.locations")
                if not isinstance(disclosure.get("human_confirmed"), bool):
                    _error(errors, "invalid_ai_disclosure_confirmation", "ai_assistance.disclosure.human_confirmed must be boolean", "ai_assistance.disclosure.human_confirmed")

    policy = packet.get("policy", {})
    if not isinstance(policy, dict):
        _error(errors, "invalid_policy", "policy must be an object", "policy")

    diff = packet.get("diff", {})
    if not isinstance(diff, dict):
        _error(errors, "invalid_diff", "diff must be an object", "diff")
    else:
        for field in PR_DIFF_FIELDS:
            if field not in diff:
                _error(errors, "missing_diff_field", f"Required PR Diff field is missing: {field}", f"diff.{field}")
        if diff.get("comparison") != "merge_base":
            _error(errors, "invalid_diff_comparison", "diff.comparison must be merge_base", "diff.comparison")
        changed_files = diff.get("changed_files", [])
        if not isinstance(changed_files, list):
            _error(errors, "invalid_changed_files", "diff.changed_files must be a list", "diff.changed_files")
        elif not all(isinstance(item, str) for item in changed_files):
            _error(errors, "invalid_changed_file", "diff.changed_files items must be strings", "diff.changed_files")
        for count_key in ("additions", "deletions"):
            if count_key in diff and (not isinstance(diff[count_key], int) or isinstance(diff[count_key], bool) or diff[count_key] < 0):
                _error(errors, "invalid_diff_count", f"diff.{count_key} must be a non-negative integer", f"diff.{count_key}")
        for sha_key in PR_DIFF_STRING_FIELDS:
            if sha_key in diff and (not isinstance(diff[sha_key], str) or not diff[sha_key].strip()):
                _error(errors, "invalid_diff_receipt", f"diff.{sha_key} must be a non-empty string when present", f"diff.{sha_key}")
        if diff.get("fingerprint_algorithm") != FINGERPRINT_ALGORITHM:
            _error(
                errors,
                "invalid_fingerprint_algorithm",
                f"diff.fingerprint_algorithm must be {FINGERPRINT_ALGORITHM}",
                "diff.fingerprint_algorithm",
            )

    verification = packet.get("verification", {})
    if not isinstance(verification, dict):
        _error(errors, "invalid_verification", "verification must be an object", "verification")
    else:
        for key in sorted(set(verification) - {"plan", "plan_digest", "receipts"}):
            _error(errors, "unknown_verification_field", f"verification.{key} is not part of Packet {PACKET_VERSION}", f"verification.{key}")
        plan = verification.get("plan")
        checks_by_id: dict[str, dict[str, Any]] = {}
        if not isinstance(plan, dict) or plan.get("plan_version") != VERIFICATION_PLAN_VERSION or not isinstance(plan.get("checks"), list):
            _error(errors, "invalid_verification_plan", f"verification.plan must be version {VERIFICATION_PLAN_VERSION} with checks", "verification.plan")
        else:
            for index, check in enumerate(plan["checks"]):
                path = f"verification.plan.checks[{index}]"
                if not isinstance(check, dict):
                    _error(errors, "invalid_verification_check", "Each verification check must be an object", path)
                    continue
                check_id = check.get("id")
                if not isinstance(check_id, str) or not check_id.strip():
                    _error(errors, "invalid_verification_check_id", "Verification check id is required", f"{path}.id")
                elif check_id in checks_by_id:
                    _error(errors, "duplicate_verification_check_id", "Verification check ids must be unique", f"{path}.id")
                else:
                    checks_by_id[check_id] = check
                if not isinstance(check.get("argv"), list) or not check.get("argv") or not all(isinstance(item, str) and item for item in check.get("argv", [])):
                    _error(errors, "invalid_verification_command", "A verification check needs a non-empty argv list", f"{path}.argv")
                cwd = check.get("cwd")
                if not isinstance(cwd, str) or not cwd.strip() or not _is_repository_relative_path(cwd):
                    _error(errors, "invalid_verification_cwd", "A verification check cwd must be repository-relative", f"{path}.cwd")
                if not isinstance(check.get("required"), bool):
                    _error(errors, "invalid_verification_required", "A verification check required flag must be boolean", f"{path}.required")
        expected_plan_digest = verification_plan_digest(plan) if isinstance(plan, dict) else ""
        if verification.get("plan_digest") != expected_plan_digest:
            _error(errors, "verification_plan_digest_mismatch", "verification.plan_digest does not match the current plan", "verification.plan_digest")
        receipts = verification.get("receipts", [])
        if not isinstance(receipts, list):
            _error(errors, "invalid_verification_receipts", "verification.receipts must be a list", "verification.receipts")
        else:
            receipt_check_ids: set[str] = set()
            for index, receipt in enumerate(receipts):
                path = f"verification.receipts[{index}]"
                if not isinstance(receipt, dict):
                    _error(errors, "invalid_verification_receipt", "Each verification receipt must be an object", path)
                    continue
                allowed_receipt = {
                    "receipt_version", "check_id", "plan_digest", "subject_digest", "argv", "cwd", "exit_code",
                    "command_outcome", "integrity_status", "started_at", "finished_at", "head_sha", "head_sha_before",
                    "head_sha_after", "worktree_clean_before", "worktree_clean_after", "failure_reason", "stdout_sha256",
                    "stderr_sha256", "provenance",
                }
                for key in sorted(set(receipt) - allowed_receipt):
                    _error(errors, "unknown_verification_receipt_field", f"{path}.{key} is not part of receipt {VERIFICATION_RECEIPT_VERSION}", f"{path}.{key}")
                if receipt.get("receipt_version") != VERIFICATION_RECEIPT_VERSION:
                    _error(errors, "invalid_verification_receipt_version", f"receipt_version must be {VERIFICATION_RECEIPT_VERSION}", f"{path}.receipt_version")
                check = checks_by_id.get(receipt.get("check_id"))
                if isinstance(receipt.get("check_id"), str) and receipt["check_id"] in receipt_check_ids:
                    _error(errors, "duplicate_verification_receipt", "Only one current receipt is allowed per check", f"{path}.check_id")
                elif isinstance(receipt.get("check_id"), str):
                    receipt_check_ids.add(receipt["check_id"])
                if check is None:
                    _error(errors, "unknown_verification_check", "Receipt check_id is not in the current plan", f"{path}.check_id")
                if receipt.get("plan_digest") != expected_plan_digest:
                    _error(errors, "stale_verification_plan", "Receipt is not bound to the current verification plan", f"{path}.plan_digest")
                if receipt.get("subject_digest") != (diff.get("subject_digest") if isinstance(diff, dict) else None):
                    _error(errors, "stale_verification_subject", "Receipt is not bound to the current contribution subject", f"{path}.subject_digest")
                if not isinstance(receipt.get("argv"), list) or not receipt.get("argv") or not all(isinstance(item, str) and item for item in receipt["argv"]):
                    _error(errors, "invalid_verification_command", "A verification receipt needs a non-empty argv list", f"{path}.argv")
                if not isinstance(receipt.get("cwd"), str) or not receipt.get("cwd", "").strip():
                    _error(errors, "invalid_verification_cwd", "A verification receipt needs cwd", f"{path}.cwd")
                elif not _is_repository_relative_path(receipt["cwd"]):
                    _error(errors, "absolute_verification_cwd", "A verification receipt cwd must be repository-relative", f"{path}.cwd")
                if isinstance(check, dict) and (receipt.get("argv") != check.get("argv") or receipt.get("cwd") != check.get("cwd")):
                    _error(errors, "verification_check_mismatch", "Receipt command and cwd must match its planned check", path)
                if not isinstance(receipt.get("head_sha"), str) or not receipt.get("head_sha", "").strip():
                    _error(errors, "invalid_verification_head", "A verification receipt needs head_sha", f"{path}.head_sha")
                if not isinstance(receipt.get("exit_code"), int) or isinstance(receipt.get("exit_code"), bool):
                    _error(errors, "invalid_verification_exit_code", "A verification receipt needs an integer exit_code", f"{path}.exit_code")
                elif receipt.get("command_outcome") != ("passed" if receipt["exit_code"] == 0 else "failed"):
                    _error(errors, "verification_outcome_mismatch", "command_outcome must match exit_code", f"{path}.command_outcome")
                if receipt.get("command_outcome") not in {"passed", "failed"}:
                    _error(errors, "invalid_verification_outcome", "command_outcome must be passed or failed", f"{path}.command_outcome")
                if receipt.get("integrity_status") not in {"stable", "invalid"}:
                    _error(errors, "invalid_verification_integrity", "integrity_status must be stable or invalid", f"{path}.integrity_status")
                stable_proof = (
                    receipt.get("head_sha_before") == receipt.get("head_sha") == receipt.get("head_sha_after")
                    and receipt.get("worktree_clean_before") is True
                    and receipt.get("worktree_clean_after") is True
                )
                if receipt.get("integrity_status") == "stable" and not stable_proof:
                    _error(errors, "verification_integrity_mismatch", "stable integrity requires matching HEAD and clean worktree proof", f"{path}.integrity_status")
                if receipt.get("provenance") != "contributor_local":
                    _error(errors, "invalid_verification_provenance", "verification receipt provenance must be contributor_local", f"{path}.provenance")

    ownership = packet.get("ownership")
    if not isinstance(ownership, dict):
        _error(errors, "invalid_ownership", "ownership must be an object", "ownership")
    else:
        allowed_ownership = {"status", "problem", "scope", "verification", "risks"}
        for key in sorted(set(ownership) - allowed_ownership):
            _error(errors, "unknown_ownership_field", f"ownership.{key} is not part of Packet {PACKET_VERSION}", f"ownership.{key}")
        if ownership.get("status") not in ALLOWED_STATUSES:
            _error(errors, "invalid_ownership_status", "ownership.status must be a result status", "ownership.status")
        for field in ("problem", "scope", "verification"):
            if not isinstance(ownership.get(field), str):
                _error(errors, "invalid_ownership_field", f"ownership.{field} must be a string", f"ownership.{field}")
        if not isinstance(ownership.get("risks"), list) or not all(isinstance(item, str) for item in ownership.get("risks", [])):
            _error(errors, "invalid_ownership_risks", "ownership.risks must be a list of strings", "ownership.risks")
        if ownership.get("status") == "passed":
            for field in ("problem", "scope", "verification"):
                if not isinstance(ownership.get(field), str) or not ownership.get(field, "").strip():
                    _error(errors, "incomplete_ownership_check", f"A passed ownership check needs {field}", f"ownership.{field}")
            if not isinstance(ownership.get("risks"), list) or not all(isinstance(item, str) and item.strip() for item in ownership.get("risks", [])):
                _error(errors, "incomplete_ownership_check", "ownership.risks must be a list of non-empty strings", "ownership.risks")

    snapshots = packet.get("snapshots", {})
    if not isinstance(snapshots, dict):
        _error(errors, "invalid_snapshots", "snapshots must be an object", "snapshots")
    else:
        expected = semantic_snapshot(packet)
        if snapshots.get("semantic") != expected:
            _error(
                errors,
                "semantic_snapshot_mismatch",
                "snapshots.semantic does not match the current semantic contribution state",
                "snapshots.semantic",
            )

    results = packet.get("results", [])
    result_by_node: dict[str, dict[str, Any]] = {}
    if not isinstance(results, list):
        _error(errors, "invalid_results", "results must be a list", "results")
    else:
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                _error(errors, "invalid_result_record", "Each result must be an object", f"results[{index}]")
                continue
            node = result.get("node")
            status = result.get("status")
            if not isinstance(node, str) or not node:
                _error(errors, "invalid_result_node", "Result node must be a non-empty string", f"results[{index}].node")
            if status not in ALLOWED_STATUSES:
                _error(errors, "invalid_result_status", f"Result status must be one of {sorted(ALLOWED_STATUSES)}", f"results[{index}].status")
            if node in result_by_node:
                _error(errors, "duplicate_result_node", f"Duplicate result for node {node}", f"results[{index}].node")
            elif isinstance(node, str):
                result_by_node[node] = result
        for node in REQUIRED_NODES:
            if node not in result_by_node:
                _error(errors, "missing_result_record", f"Every flow node needs a result record: {node}", "results")

    review_profile = review.get("profile") if isinstance(review, dict) else "standard"
    understanding = packet.get("understanding", {})
    for error in validate_understanding(understanding, semantic_snapshot(packet), review_profile=review_profile)["errors"]:
        _error(errors, error["code"], error["message"], error["path"])

    narrative = packet.get("narrative", {})
    if not isinstance(narrative, dict):
        _error(errors, "invalid_narrative", "narrative must be an object", "narrative")
    else:
        if not isinstance(narrative.get("title"), str) or not narrative.get("title", "").strip():
            _error(errors, "missing_pr_title", "Final PR title is required", "narrative.title")
        if not isinstance(narrative.get("body"), str) or not narrative.get("body", "").strip():
            _error(errors, "missing_pr_body", "Final PR Body is required", "narrative.body")
        if narrative.get("final_preview_confirmed") is not True:
            _error(errors, "narrative_not_confirmed", "Final PR title and Body must be previewed and confirmed", "narrative.final_preview_confirmed")
        if (narrative.get("human_expression_required") or (isinstance(review, dict) and review.get("profile") == "heightened")) and not str(narrative.get("human_expression", "")).strip():
            _error(errors, "missing_human_expression", "This contribution requires human-authored motivation/trade-offs/risk", "narrative.human_expression")

    candidate_selection = packet.get("candidate_selection")
    if candidate_selection is not None:
        if not isinstance(candidate_selection, dict):
            _error(errors, "invalid_candidate_selection", "candidate_selection must be an object", "candidate_selection")
        else:
            disposition = candidate_selection.get("duplicate_disposition")
            if disposition not in DUPLICATE_DISPOSITIONS:
                _error(errors, "invalid_duplicate_disposition", "candidate_selection.duplicate_disposition is required", "candidate_selection.duplicate_disposition")
            recommendation = candidate_selection.get("recommendation")
            if recommendation is not None and recommendation not in RECOMMENDATIONS:
                _error(errors, "invalid_candidate_recommendation", "candidate_selection.recommendation must be a recognized recommendation when present", "candidate_selection.recommendation")
            transition = candidate_selection.get("transition")
            if transition is not None:
                if not isinstance(transition, dict):
                    _error(errors, "invalid_candidate_transition", "candidate_selection.transition must be an object", "candidate_selection.transition")
                else:
                    if transition.get("from") not in {"issue_only", "seek_maintainer_signal"}:
                        _error(errors, "invalid_candidate_transition_from", "candidate_selection.transition.from must be an advisory recommendation", "candidate_selection.transition.from")
                    if recommendation in {"issue_only", "seek_maintainer_signal"} and transition.get("from") != recommendation:
                        _error(errors, "candidate_transition_origin_mismatch", "candidate_selection.transition.from must match candidate_selection.recommendation", "candidate_selection.transition.from")
                    if transition.get("to") != "plan_directly":
                        _error(errors, "invalid_candidate_transition_to", "candidate_selection.transition.to must be plan_directly", "candidate_selection.transition.to")
                    if not isinstance(transition.get("reason"), str) or not transition.get("reason", "").strip():
                        _error(errors, "missing_candidate_transition_reason", "candidate_selection.transition.reason is required", "candidate_selection.transition.reason")
                    if transition.get("human_confirmed") is not True:
                        _error(errors, "candidate_transition_not_confirmed", "candidate_selection.transition needs human_confirmed=true", "candidate_selection.transition.human_confirmed")

    return {"valid": not errors, "errors": errors, "result_nodes": sorted(result_by_node)}


def validate_packet(packet: Any) -> dict[str, Any]:
    """Validate any JSON-like value and always return structured errors."""

    format_errors = packet_format_errors(packet)
    if format_errors:
        return {
            "valid": False,
            "errors": format_errors,
            "result_nodes": [],
        }
    try:
        return _validate_packet_object(packet)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {
            "valid": False,
            "errors": [{"code": "invalid_packet_structure", "message": str(exc), "path": "packet"}],
            "result_nodes": [],
        }


def deterministic_evidence_checks(
    packet: dict[str, Any],
    changed_files: list[str] | None = None,
    *,
    strict: bool = False,
) -> tuple[list[dict[str, str]], list[str]]:
    """Check file scope and diff budget without inferring missing evidence."""

    violations: list[dict[str, str]] = []
    unknowns: list[str] = []

    def add_unknown(code: str, message: str, path: str) -> None:
        if strict:
            violations.append({"code": code, "message": message, "path": path})
        else:
            unknowns.append(message)

    diff_record = packet.get("diff", {})
    if not isinstance(diff_record, dict):
        diff_record = {}
    contract = packet.get("contract", {})
    if not isinstance(contract, dict):
        contract = {}

    provided_files = changed_files if changed_files is not None else diff_record.get("changed_files")
    if not isinstance(provided_files, list):
        add_unknown("scope_unverifiable", "Changed-file evidence is not a list; scope cannot be checked.", "diff.changed_files")
        provided_files = []
    else:
        invalid_files = [item for item in provided_files if not isinstance(item, str)]
        if invalid_files:
            add_unknown("invalid_changed_files", "Changed-file evidence contains non-string values; scope cannot be checked reliably.", "diff.changed_files")
        provided_files = [item for item in provided_files if isinstance(item, str)]

    scope = contract.get("scope", {})
    if not isinstance(scope, dict):
        scope = {}
    scoped_files = {item for item in scope.get("files", []) if isinstance(item, str)}
    scoped_modules = {item for item in scope.get("modules", []) if isinstance(item, str)}
    if provided_files and scoped_files:
        extra = sorted(set(provided_files) - scoped_files)
        if extra:
            violations.append({"code": "out_of_scope_files", "message": f"Changed files are outside the approved scope: {extra}", "path": "contract.scope.files"})
    elif provided_files and scoped_modules:
        add_unknown(
            "scope_unverifiable",
            "Scope is module-based; changed-file evidence cannot be checked without a module-to-file mapping.",
            "contract.scope.modules",
        )
    else:
        add_unknown("scope_unverifiable", "Changed-file evidence was not provided; scope cannot be checked.", "diff.changed_files")

    budget = contract.get("max_diff_lines")
    if "max_diff_lines" not in contract:
        add_unknown("missing_diff_budget", "contract.max_diff_lines is required; the scope budget cannot be checked.", "contract.max_diff_lines")
    elif "additions" in diff_record and "deletions" in diff_record:
        additions = diff_record.get("additions")
        deletions = diff_record.get("deletions")
        if isinstance(budget, int) and not isinstance(budget, bool) and isinstance(additions, int) and isinstance(deletions, int):
            changed_lines = additions + deletions
            if changed_lines > budget:
                violations.append({"code": "diff_budget_exceeded", "message": f"Diff has {changed_lines} changed lines; budget is {budget}.", "path": "contract.max_diff_lines"})
        else:
            add_unknown("diff_budget_unverifiable", "Diff line counts or the scope budget are not valid integers; the budget cannot be checked.", "diff")
    else:
        add_unknown("diff_budget_unverifiable", "Diff line counts are missing; the scope budget cannot be checked.", "diff")

    return violations, unknowns


def issue_reference(packet: dict[str, Any]) -> str | None:
    """Return the canonical Issue URL supporting an Issue-backed contribution."""

    basis = packet.get("basis", {})
    if not isinstance(basis, dict):
        return None
    candidates: list[Any] = []
    if basis.get("kind") == "issue":
        candidates.extend(basis.get("references", []) if isinstance(basis.get("references", []), list) else [])
    signal = basis.get("signal")
    if isinstance(signal, dict) and signal.get("record_type") == "issue":
        candidates.append(signal.get("reference"))
    for candidate in candidates:
        parsed = parse_public_record(candidate)
        if parsed and parsed.get("record_type") == "issue":
            return str(parsed["url"])
    return None


def issue_basis_blockers(packet: dict[str, Any]) -> list[dict[str, str]]:
    """Check the local Issue evidence without making a provider call."""

    basis = packet.get("basis", {})
    if not isinstance(basis, dict) or basis.get("kind") not in {"issue", "signal"}:
        return []
    if basis.get("kind") == "signal":
        signal = basis.get("signal")
        if isinstance(signal, dict) and signal.get("record_type") != "issue":
            return []
    reference = issue_reference(packet)
    if not reference:
        return [{"code": "issue_reference_required", "message": "Issue-backed work needs a canonical GitHub Issue URL.", "path": "basis.references"}]
    repository = packet.get("repository", {})
    parsed = parse_public_record(reference)
    if not isinstance(repository, dict) or parsed is None or not repository_slugs_match(f"{parsed['owner']}/{parsed['name']}", f"{repository.get('owner')}/{repository.get('name')}"):
        return [{"code": "issue_repository_mismatch", "message": "The Issue reference must belong to the Packet repository.", "path": "basis.references"}]
    verification = basis.get("verification") if basis.get("kind") == "issue" else (basis.get("signal", {}) or {}).get("verification")
    if not isinstance(verification, dict) or verification.get("status") != "verified" or verification.get("provider") != "github" or verification.get("reference") != reference:
        return [{"code": "issue_verification_required", "message": "The Issue reference needs a recorded successful GitHub verification.", "path": "basis.verification"}]
    if verification.get("repository") and not repository_slugs_match(verification.get("repository"), f"{repository.get('owner')}/{repository.get('name')}"):
        return [{"code": "issue_verification_repository_mismatch", "message": "The recorded Issue verification belongs to another repository.", "path": "basis.verification.repository"}]
    blockers: list[dict[str, str]] = []
    state_reason = normalize_label(verification.get("state_reason", ""))
    if state_reason == "not planned":
        blockers.append({"code": "issue_not_actionable", "message": "The Issue is recorded as closed for not planned.", "path": "basis.verification.state_reason"})
    if has_normalized_label(verification.get("labels"), "duplicate"):
        blockers.append({"code": "issue_duplicate", "message": "The Issue is recorded with the duplicate label.", "path": "basis.verification.labels"})
    repository_id = repository.get("repository_id")
    if repository_id is not None and verification.get("repository_id") is None:
        blockers.append({"code": "issue_verification_identity_missing", "message": "The recorded Issue verification must include the Packet repository identity.", "path": "basis.verification.repository_id"})
    if repository_id is not None and repository_id != verification.get("repository_id"):
        blockers.append({"code": "issue_verification_identity_mismatch", "message": "The recorded Issue verification has a different repository identity.", "path": "basis.verification.repository_id"})
    return blockers


def issue_link_blockers(packet: dict[str, Any], body: str) -> list[dict[str, str]]:
    reference = issue_reference(packet)
    if reference and reference not in body:
        return [{"code": "issue_link_missing", "message": "The final PR Body must contain the canonical supporting Issue URL.", "path": "narrative.body"}]
    return []


def good_first_issue_policy_errors(
    packet: dict[str, Any],
    labels: Any,
    *,
    path: str,
) -> list[dict[str, str]]:
    """Apply the good-first AI rule to provider-verified labels only."""

    policy = packet.get("policy", {})
    claims = policy.get("authoritative_claims", {}) if isinstance(policy, dict) else {}
    ai_assistance = packet.get("ai_assistance", {})
    ai_used = ai_assistance.get("used") if isinstance(ai_assistance, dict) else None
    if (
        isinstance(claims, dict)
        and claims.get("good_first_issue_ai_allowed") is False
        and has_normalized_label(labels, "good first issue")
        and ai_used is not False
    ):
        return [{
            "code": "good_first_issue_ai_disallowed",
            "message": "The repository does not allow AI-assisted work on good-first-issue items.",
            "path": path,
        }]
    return []


def policy_violations(packet: dict[str, Any], *, enforce_disclosure: bool) -> list[dict[str, str]]:
    """Return only deterministic violations from known policy claims."""

    policy = packet.get("policy", {})

    if not isinstance(policy, dict):
        return []
    violations: list[dict[str, str]] = []
    if policy.get("conflicts"):
        violations.append({"code": "policy_conflict", "message": "Policy sources conflict.", "path": "policy.conflicts"})
    if policy.get("ambiguities"):
        violations.append({"code": "policy_ambiguity", "message": "A policy source contains opposed explicit claims.", "path": "policy.ambiguities"})

    claims = policy.get("authoritative_claims", {})
    if not isinstance(claims, dict):
        claims = {}
    if enforce_disclosure:
        violations.extend(disclosure_errors(packet))

    ai_assistance = packet.get("ai_assistance", {})
    ai_used = ai_assistance.get("used") if isinstance(ai_assistance, dict) else None
    if claims.get("ai_assistance") == "prohibited" and ai_used is not False:
        violations.append({"code": "ai_assistance_prohibited", "message": "The repository policy prohibits AI assistance for this contribution.", "path": "ai_assistance.used"})
    if claims.get("issue_required") is True:
        basis = packet.get("basis", {})
        basis_kind = basis.get("kind") if isinstance(basis, dict) else None
        if basis_kind != "issue":
            violations.append({"code": "issue_required", "message": "The repository policy requires an Issue-backed contribution.", "path": "basis.kind"})

    entry = packet.get("entry", {})
    basis = packet.get("basis", {})
    if claims.get("discovery_evidence_allowed") is False and (
        (isinstance(entry, dict) and entry.get("mode") == "discovery")
        or (isinstance(basis, dict) and basis.get("kind") == "discovery-evidence")
    ):
        violations.append({"code": "discovery_evidence_disallowed", "message": "Repository policy does not allow Discovery evidence as the contribution basis.", "path": "basis.kind"})

    narrative = packet.get("narrative", {})
    if not isinstance(narrative, dict):
        narrative = {}
    if claims.get("human_pr_narrative_required") is True and not str(narrative.get("human_expression", "")).strip():
        violations.append({"code": "missing_human_expression", "message": "The repository policy requires human-owned PR motivation and trade-offs.", "path": "narrative.human_expression"})
    if isinstance(basis, dict) and basis.get("kind") == "issue":
        verification = basis.get("verification")
        labels_path = "basis.verification.labels"
        issue_label_target = True
    elif (
        isinstance(basis, dict)
        and basis.get("kind") == "signal"
        and isinstance(basis.get("signal"), dict)
        and basis["signal"].get("record_type") == "issue"
    ):
        verification = basis["signal"].get("verification")
        labels_path = "basis.signal.verification.labels"
        issue_label_target = True
    else:
        verification = None
        labels_path = "basis.verification.labels"
        issue_label_target = False
    repository = packet.get("repository", {})
    reference = issue_reference(packet)
    expected_repository = (
        f"{repository.get('owner')}/{repository.get('name')}"
        if isinstance(repository, dict) and repository.get("owner") and repository.get("name")
        else None
    )
    parsed_reference = parse_public_record(reference) if reference is not None else None
    trusted_verification = (
        isinstance(verification, dict)
        and verification.get("status") == "verified"
        and verification.get("provider") == "github"
        and verification.get("record_type") == "issue"
        and parsed_reference is not None
        and verification.get("reference") == reference
        and verification.get("host") == "github.com"
        and verification.get("url") == reference
        and isinstance(verification.get("number"), int)
        and not isinstance(verification.get("number"), bool)
        and verification.get("number") == parsed_reference.get("number")
        and verification.get("visibility") == "public"
        and isinstance(verification.get("labels"), list)
        and all(isinstance(label, str) for label in verification.get("labels"))
        and expected_repository is not None
        and repository_slugs_match(verification.get("repository"), expected_repository)
        and isinstance(repository.get("repository_id"), int)
        and not isinstance(repository.get("repository_id"), bool)
        and repository.get("repository_id") > 0
        and isinstance(verification.get("repository_id"), int)
        and not isinstance(verification.get("repository_id"), bool)
        and verification.get("repository_id") == repository.get("repository_id")
    )
    trusted_labels = verification.get("labels") if trusted_verification else []
    if (
        claims.get("good_first_issue_ai_allowed") is False
        and ai_used is not False
        and issue_label_target
        and not trusted_verification
    ):
        violations.append({
            "code": "good_first_issue_label_verification_required",
            "message": "The good-first-issue AI policy requires a complete verified GitHub Issue identity and labels.",
            "path": labels_path,
        })
    else:
        violations.extend(good_first_issue_policy_errors(packet, trusted_labels, path=labels_path))
    return violations


def _readiness_blockers_object(packet: dict[str, Any]) -> list[dict[str, str]]:
    validation = validate_packet(packet)
    blockers = list(validation["errors"])

    evidence_violations, _unknowns = deterministic_evidence_checks(packet, strict=True)
    blockers.extend(evidence_violations)

    entry = packet.get("entry", {})
    basis = packet.get("basis", {})
    review = packet.get("review", {})
    if isinstance(review, dict) and review.get("signals") and review.get("profile") == "standard":
        blockers.append({"code": "review_profile_too_low", "message": "Risk signals require a full review profile.", "path": "review.profile"})
    for stop in review.get("hard_stops", []) if isinstance(review, dict) and isinstance(review.get("hard_stops", []), list) else []:
        if isinstance(stop, dict):
            blockers.append({"code": "hard_stop", "message": str(stop.get("reason", stop)), "path": "review.hard_stops"})
        else:
            blockers.append({"code": "hard_stop", "message": str(stop), "path": "review.hard_stops"})

    policy = packet.get("policy", {})

    candidate_selection = packet.get("candidate_selection")
    if isinstance(candidate_selection, dict):
        if candidate_selection.get("duplicate_disposition") in DUPLICATE_BLOCKING_DISPOSITIONS:
            blockers.append(
                {
                    "code": "duplicate_work_unresolved",
                    "message": f"Candidate duplicate disposition {candidate_selection['duplicate_disposition']} blocks implementation until resolved.",
                    "path": "candidate_selection.duplicate_disposition",
                }
            )
        recommendation = candidate_selection.get("recommendation")
        if recommendation == "do_not_contribute":
            blockers.append({"code": "candidate_do_not_contribute", "message": "The selected candidate is explicitly marked do_not_contribute.", "path": "candidate_selection.recommendation"})
        elif recommendation in {"issue_only", "seek_maintainer_signal"}:
            transition = candidate_selection.get("transition")
            if (
                not isinstance(transition, dict)
                or transition.get("from") != recommendation
                or transition.get("to") != "plan_directly"
                or not isinstance(transition.get("reason"), str)
                or not transition.get("reason", "").strip()
                or transition.get("human_confirmed") is not True
            ):
                blockers.append({"code": "candidate_transition_required", "message": f"The {recommendation} recommendation needs a human-confirmed transition to plan_directly before readiness.", "path": "candidate_selection.transition"})

    for result in packet.get("results", []) if isinstance(packet.get("results", []), list) else []:
        if isinstance(result, dict) and result.get("status") != "passed":
            blockers.append(
                {
                    "code": "node_not_passed",
                    "message": f"Flow node {result.get('node', '<unknown>')} has status {result.get('status')}",
                    "path": "results",
                }
            )
        elif isinstance(result, dict) and result.get("status") == "passed" and not result.get("evidence"):
            blockers.append({"code": "missing_result_evidence", "message": f"Passed flow node {result.get('node', '<unknown>')} needs evidence.", "path": "results"})

    contract = packet.get("contract", {})
    approval = contract.get("approval") if isinstance(contract, dict) else None
    if not isinstance(approval, dict) or approval.get("status") != "approved" or approval.get("human_confirmed") is not True:
        blockers.append({"code": "contract_not_approved", "message": "The contribution contract needs explicit human approval before remote readiness.", "path": "contract.approval"})

    ownership = packet.get("ownership", {})
    if not isinstance(ownership, dict) or ownership.get("status") != "passed":
        blockers.append({"code": "ownership_not_passed", "message": "The contributor Ownership Check must pass before remote readiness.", "path": "ownership.status"})

    verification = packet.get("verification", {})
    plan = verification.get("plan", {}) if isinstance(verification, dict) else {}
    checks = plan.get("checks", []) if isinstance(plan, dict) else []
    required_checks = {
        check.get("id"): check
        for check in checks
        if isinstance(check, dict) and check.get("required") is True and isinstance(check.get("id"), str)
    } if isinstance(checks, list) else {}
    if not required_checks:
        blockers.append({"code": "missing_verification_plan", "message": "Remote readiness requires at least one required verification check.", "path": "verification.plan.checks"})
    receipts = verification.get("receipts", []) if isinstance(verification, dict) else []
    usable_receipts = [
        receipt for receipt in receipts
        if isinstance(receipt, dict)
        and receipt.get("receipt_version") == VERIFICATION_RECEIPT_VERSION
        and receipt.get("provenance") == "contributor_local"
        and receipt.get("command_outcome") == "passed"
        and receipt.get("exit_code") == 0
        and receipt.get("integrity_status") == "stable"
        and receipt.get("plan_digest") == (verification.get("plan_digest") if isinstance(verification, dict) else None)
        and receipt.get("subject_digest") == (packet.get("diff", {}).get("subject_digest") if isinstance(packet.get("diff"), dict) else None)
        and isinstance(receipt.get("argv"), list)
        and receipt.get("argv")
        and isinstance(receipt.get("cwd"), str)
        and receipt.get("cwd")
        and isinstance(receipt.get("head_sha"), str)
        and receipt.get("head_sha")
        and receipt.get("head_sha_before") == receipt.get("head_sha") == receipt.get("head_sha_after")
        and receipt.get("worktree_clean_before") is True
        and receipt.get("worktree_clean_after") is True
    ] if isinstance(receipts, list) else []
    if not usable_receipts:
        blockers.append({"code": "missing_executed_verification", "message": "Remote readiness needs a current contributor-local passing receipt.", "path": "verification.receipts"})
    passed_check_ids = {receipt.get("check_id") for receipt in usable_receipts}
    missing_check_ids = sorted(set(required_checks) - passed_check_ids)
    if missing_check_ids:
        blockers.append({"code": "required_verification_missing", "message": f"Required verification checks have no current passing receipt: {missing_check_ids}", "path": "verification.receipts"})

    diff = packet.get("diff", {})
    if (
        not isinstance(diff, dict)
        or diff.get("comparison") != "merge_base"
        or not all(isinstance(diff.get(key), str) and diff.get(key) for key in PR_DIFF_STRING_FIELDS)
    ):
        blockers.append({"code": "missing_diff_receipt", "message": "Remote readiness needs a merge-base PR Diff receipt bound to base tip, merge base, and head.", "path": "diff"})
    elif usable_receipts and not any(receipt.get("head_sha") == diff.get("head_sha") for receipt in usable_receipts):
        blockers.append({"code": "verification_head_mismatch", "message": "No executed verification receipt matches diff.head_sha.", "path": "verification.receipts"})

    blockers.extend(policy_violations(packet, enforce_disclosure=True))

    if isinstance(basis, dict):
        blockers.extend(issue_basis_blockers(packet))
        blockers.extend(signal_readiness_blockers(basis, entry.get("mode") if isinstance(entry, dict) else ""))
        if basis.get("kind") == "discovery-evidence":
            claims = policy.get("authoritative_claims", {}) if isinstance(policy, dict) else {}
            if not isinstance(claims, dict):
                claims = {}
            if claims.get("discovery_evidence_allowed") is not True:
                if claims.get("discovery_evidence_allowed") is False:
                    pass
                else:
                    blockers.append(
                        {
                            "code": "discovery_evidence_policy_unknown",
                            "message": "Reproducible Discovery evidence needs an explicit policy allowance before remote readiness.",
                            "path": "policy.authoritative_claims.discovery_evidence_allowed",
                        }
                    )

    if isinstance(review, dict) and review.get("profile") in {"heightened", "learning"}:
        understanding = packet.get("understanding", {}) if isinstance(packet.get("understanding", {}), dict) else {}
        orientation = understanding.get("orientation", {})
        if not isinstance(orientation, dict) or orientation.get("status") != "passed":
            blockers.append({"code": "orientation_not_passed", "message": "The selected review profile requires a passed Orientation.", "path": "understanding.orientation.status"})
        elif orientation.get("semantic_snapshot") != semantic_snapshot(packet):
            blockers.append({"code": "stale_orientation", "message": "Understanding Orientation is stale.", "path": "understanding.orientation.semantic_snapshot"})
        assessment = understanding.get("assessment", {}) if isinstance(understanding, dict) else {}
        if not isinstance(assessment, dict) or assessment.get("status") != "passed":
            blockers.append({"code": "assessment_not_passed", "message": "The selected review profile requires a passed Assessment.", "path": "understanding.assessment.status"})
        elif assessment.get("semantic_snapshot") != semantic_snapshot(packet):
            blockers.append({"code": "stale_assessment", "message": "Understanding Assessment is stale.", "path": "understanding.assessment.semantic_snapshot"})
    return blockers


def readiness_blockers(packet: Any) -> list[dict[str, str]]:
    """Evaluate readiness for any JSON-like value without throwing."""

    validation = validate_packet(packet)
    if packet_format_errors(packet):
        return list(validation["errors"])
    try:
        return _readiness_blockers_object(packet)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return [
            *validation["errors"],
            {"code": "invalid_readiness_structure", "message": str(exc), "path": "packet"},
        ]
