"""Derived contributor workflow status and deterministic next-step hints."""

from __future__ import annotations

from pathlib import Path
import shlex
from typing import Any

from .packet import issue_reference, readiness_blockers, validate_packet


_STAGE_CODES = (
    ("basis", {"issue_reference_required", "issue_verification_required", "signal_verification_required", "missing_signal_record", "discovery_signal_required"}),
    ("contract", {"contract_not_approved", "candidate_transition_required", "duplicate_work_unresolved"}),
    ("diff", {"missing_diff_receipt"}),
    ("verification", {"missing_verification_plan", "missing_executed_verification", "required_verification_missing", "verification_head_mismatch"}),
    ("ownership", {"ownership_not_passed"}),
    ("understanding", {"orientation_not_passed", "assessment_not_passed", "stale_orientation", "stale_assessment"}),
    ("narrative", {"missing_human_expression", "missing_result_evidence", "node_not_passed"}),
)


def _deduplicated(items: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (str(item.get("code", "")), str(item.get("path", "")), str(item.get("message", "")))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _current_receipt_ids(packet: dict[str, Any]) -> set[str]:
    verification = packet.get("verification") if isinstance(packet.get("verification"), dict) else {}
    plan_digest = verification.get("plan_digest")
    diff = packet.get("diff") if isinstance(packet.get("diff"), dict) else {}
    subject_digest = diff.get("subject_digest")
    receipts = verification.get("receipts", [])
    if not isinstance(receipts, list):
        return set()
    return {
        str(receipt.get("check_id"))
        for receipt in receipts if isinstance(receipt, dict)
        and receipt.get("receipt_version") == "0.3"
        and receipt.get("plan_digest") == plan_digest
        and receipt.get("subject_digest") == subject_digest
        and receipt.get("command_outcome") == "passed"
        and receipt.get("integrity_status") == "stable"
        and receipt.get("provenance") == "contributor_local"
        and receipt.get("head_sha") == diff.get("head_sha")
        and receipt.get("head_sha_before") == receipt.get("head_sha") == receipt.get("head_sha_after")
        and receipt.get("worktree_clean_before") is True
        and receipt.get("worktree_clean_after") is True
        and isinstance(receipt.get("argv"), list) and bool(receipt.get("argv"))
        and isinstance(receipt.get("cwd"), str) and bool(receipt.get("cwd"))
    }


def _next_actions(packet: dict[str, Any], packet_path: Path, stage: str) -> list[dict[str, str]]:
    quoted_packet = shlex.quote(str(packet_path))
    if stage == "basis":
        if issue_reference(packet):
            return [{"kind": "command", "command": f"reviewworthy issue verify --packet {quoted_packet} --record --json", "reason": "Record current provider evidence for the Issue contribution basis."}]
        basis = packet.get("basis") if isinstance(packet.get("basis"), dict) else {}
        signal = basis.get("signal") if isinstance(basis.get("signal"), dict) else {}
        if signal.get("record_type") in {"pull_request", "discussion"}:
            return [{"kind": "decision", "command": "", "reason": "Verify the source Signal artifact with `reviewworthy signal verify SIGNAL_PATH --record --json`, then bind that updated Signal 0.3 record to this Packet."}]
        return [{"kind": "decision", "command": "", "reason": "Create or repair the required Signal 0.3 contribution basis and bind it to this Packet."}]
    if stage == "contract":
        return [{"kind": "decision", "command": "", "reason": "Resolve candidate disposition and explicitly approve the bounded Contribution Contract."}]
    if stage == "diff":
        return [{"kind": "command", "command": "reviewworthy diff capture --root . --base BASE --head HEAD --json", "reason": "Capture the canonical merge-base contribution subject, then bind it to the Packet."}]
    if stage == "verification":
        verification = packet.get("verification") if isinstance(packet.get("verification"), dict) else {}
        plan = verification.get("plan") if isinstance(verification.get("plan"), dict) else {}
        checks = plan.get("checks", [])
        current_ids = _current_receipt_ids(packet)
        missing_ids = [
            str(check.get("id")) for check in checks
            if isinstance(checks, list) and isinstance(check, dict) and check.get("required") is True
            and isinstance(check.get("id"), str) and check["id"] not in current_ids
        ]
        if missing_ids:
            return [
                {
                    "kind": "command",
                    "command": f"reviewworthy verify run --root . --packet {quoted_packet} --check-id {shlex.quote(check_id)} --json",
                    "reason": f"Run required current check {check_id}.",
                }
                for check_id in missing_ids
            ]
        return [{"kind": "decision", "command": "", "reason": "Define at least one required verification-plan check."}]
    if stage == "ownership":
        return [{"kind": "decision", "command": "", "reason": "Complete the light Ownership Check: problem, scope, verification, and risks."}]
    if stage == "understanding":
        return [{"kind": "command", "command": f"reviewworthy understanding validate {quoted_packet} --json", "reason": "Inspect the Heightened/Learning understanding gaps, then record current Orientation and Assessment."}]
    if stage == "narrative":
        return [{"kind": "decision", "command": "", "reason": "Finish remaining flow evidence and the human-owned PR narrative."}]
    if stage == "invalid":
        return [{"kind": "command", "command": f"reviewworthy packet validate {quoted_packet} --json", "reason": "Repair the current Packet 0.3 structure before continuing."}]
    if stage == "blocked":
        return [{"kind": "decision", "command": "", "reason": "Resolve the remaining policy, security, or hard-stop findings before continuing."}]
    return [{"kind": "command", "command": "reviewworthy remote plan ...", "reason": "The Packet is ready for an explicit remote-write plan."}]


def workflow_status(packet: Any, packet_path: Path) -> dict[str, Any]:
    validation = validate_packet(packet)
    validation_errors = list(validation.get("errors", []))
    readiness = readiness_blockers(packet)
    blockers = _deduplicated([*validation_errors, *readiness])
    if validation_errors or not isinstance(packet, dict):
        stage = "invalid"
    elif not blockers:
        stage = "ready"
    else:
        codes = {item.get("code") for item in blockers}
        stage = next((name for name, stage_codes in _STAGE_CODES if codes & stage_codes), "blocked")
    return {
        "status_version": "0.3",
        "packet": str(packet_path),
        "current_stage": stage,
        "ready": not blockers,
        "blocking": blockers,
        "next": _next_actions(packet if isinstance(packet, dict) else {}, packet_path, stage),
    }
