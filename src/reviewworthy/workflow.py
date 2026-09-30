"""Derived contributor workflow status and deterministic next-step hints."""

from __future__ import annotations

from pathlib import Path
import shlex
from typing import Any

from .contract import validate_contract
from .github import GhError, build_operation, load_operation_state
from .packet import current_verification_receipts, issue_reference, readiness_blockers, validate_packet
from .repository import repository_matches


_STAGE_CODES = (
    ("basis", {
        "empty_basis", "missing_signal_record", "missing_signal_reference", "missing_signal_evidence",
        "missing_signal_authority", "issue_reference_required", "issue_verification_required",
        "signal_verification_required", "discovery_signal_required",
    }),
    ("contract", {"empty_scope", "contract_not_approved", "candidate_transition_required", "duplicate_work_unresolved"}),
    ("profile", {"review_profile_too_low"}),
    ("implementation", {
        "invalid_diff_receipt", "missing_diff_receipt", "scope_unverifiable", "out_of_scope_files",
        "diff_budget_exceeded", "diff_budget_unverifiable",
    }),
    ("verification", {
        "missing_verification_plan", "missing_executed_verification", "required_verification_missing",
        "stale_verification_plan", "stale_verification_subject", "verification_head_mismatch",
    }),
    ("ownership", {"ownership_not_passed"}),
    ("understanding", {
        "orientation_not_passed", "assessment_not_passed", "stale_orientation", "stale_assessment",
        "assessment_requires_orientation", "assessment_requires_current_orientation",
    }),
    ("narrative", {
        "missing_pr_title", "missing_pr_body", "narrative_not_confirmed", "missing_ai_disclosure",
        "missing_disclosure_location", "disclosure_not_human_confirmed", "missing_human_expression", "missing_disclosure_stage",
        "disclosure_not_in_pr_body", "disclosure_overclaims_verification",
    }),
)

_RESULT_STAGE_NODES = {
    "basis": {"policy_check", "contribution_basis"},
    "contract": {"contribution_contract"},
    "implementation": {"implementation"},
    "verification": {"verification"},
    "ownership": {"ownership"},
    "narrative": {"narrative"},
}

_HARD_STOP_CODES = {
    "hard_stop",
    "candidate_do_not_contribute",
    "policy_conflict",
    "policy_ambiguity",
    "policy_invalid_configuration",
    "policy_source_missing",
    "policy_source_unsupported",
    "policy_source_unreadable",
    "policy_source_encoding",
    "policy_source_limit",
    "policy_source_path_invalid",
    "policy_scan_unavailable",
    "ai_assistance_prohibited",
    "good_first_issue_ai_disallowed",
}

_EXPECTED_INCOMPLETE_CODES = {
    *set().union(*(codes for _, codes in _STAGE_CODES)),
    "missing_result_evidence",
    "node_not_passed",
}


def _deduplicated(items: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (str(item.get("code", "")), str(item.get("path", "")), str(item.get("message", "")))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _incomplete_result_nodes(packet: dict[str, Any]) -> set[str]:
    results = packet.get("results", [])
    if not isinstance(results, list):
        return set()
    return {
        str(result.get("node"))
        for result in results
        if isinstance(result, dict)
        and isinstance(result.get("node"), str)
        and (result.get("status") != "passed" or not result.get("evidence"))
    }


def _has_hard_stop(packet: dict[str, Any], blockers: list[dict[str, str]]) -> bool:
    review = packet.get("review") if isinstance(packet.get("review"), dict) else {}
    hard_stops = review.get("hard_stops", [])
    if isinstance(hard_stops, list) and hard_stops:
        return True
    return bool({item.get("code") for item in blockers} & _HARD_STOP_CODES)


def _derived_stage(packet: dict[str, Any], blockers: list[dict[str, str]]) -> str:
    codes = {item.get("code") for item in blockers}
    incomplete_nodes = _incomplete_result_nodes(packet)
    for stage, stage_codes in _STAGE_CODES:
        if stage == "implementation" and "missing_verification_plan" in codes:
            return "verification"
        if codes & stage_codes or incomplete_nodes & _RESULT_STAGE_NODES.get(stage, set()):
            return stage
    return "blocked"


def _current_receipt_ids(packet: dict[str, Any]) -> set[str]:
    return {str(receipt["check_id"]) for receipt in current_verification_receipts(packet)}


def _next_actions(packet: dict[str, Any], packet_path: Path, stage: str) -> list[dict[str, str]]:
    quoted_packet = shlex.quote(str(packet_path))
    if stage == "basis":
        policy = packet.get("policy", {})
        policy_recorded = isinstance(policy, dict) and policy.get("result") in {"passed", "blocked"}
        policy_recorded = policy_recorded or any(
            isinstance(record, dict) and record.get("node") == "policy_check"
            and record.get("status") == "passed" and record.get("evidence")
            for record in packet.get("results", [])
        )
        if not policy_recorded:
            return [{"kind": "command", "command": f"reviewworthy packet policy bind --root . --packet {quoted_packet} --json", "reason": "Bind repository policy from the current checkout before contribution decisions."}]
        if issue_reference(packet):
            return [{"kind": "command", "command": f"reviewworthy issue verify --packet {quoted_packet} --record --json", "reason": "Record current provider evidence for the Issue contribution basis."}]
        basis = packet.get("basis") if isinstance(packet.get("basis"), dict) else {}
        if basis.get("kind") == "issue":
            return [{"kind": "decision", "command": "", "reason": f"Choose the canonical GitHub Issue URL, then record it with `reviewworthy packet basis record --packet {quoted_packet} --issue URL --json`."}]
        signal = basis.get("signal") if isinstance(basis.get("signal"), dict) else {}
        if signal.get("record_type") in {"pull_request", "discussion"}:
            return [{"kind": "decision", "command": "", "reason": f"Verify the source Signal artifact with `reviewworthy signal verify SIGNAL_PATH --record --json`, then bind it with `reviewworthy packet basis record --packet {quoted_packet} --signal SIGNAL_PATH --json`."}]
        return [{"kind": "decision", "command": "", "reason": f"Create or repair the Signal 0.3 basis, then bind it with `reviewworthy packet basis record --packet {quoted_packet} --signal SIGNAL_PATH --json`; local evidence needs a Packet repository identity and explicit policy allowance."}]
    if stage == "contract":
        selection = packet.get("candidate_selection", {})
        if isinstance(selection, dict) and selection.get("recommendation") in {"issue_only", "seek_maintainer_signal", "do_not_contribute"} and not selection.get("transition"):
            return [{"kind": "decision", "command": "", "reason": "Resolve candidate disposition with an explicit human-confirmed transition and reason before Contract approval."}]
        contract = packet.get("contract", {})
        unapproved = dict(contract)
        unapproved["approval"] = {"status": "not_run", "human_confirmed": False}
        if not validate_contract(unapproved)["valid"]:
            return [{"kind": "decision", "command": "", "reason": f"Write the bounded Contract fields, then embed them with `reviewworthy packet contract bind --packet {quoted_packet} --contract FILE --json`."}]
        return [{"kind": "decision", "command": "", "reason": f"Resolve any candidate disposition and obtain explicit human approval of the embedded Contract, then run `reviewworthy packet contract approve --packet {quoted_packet} --human-confirmed --json`."}]
    if stage == "profile":
        return [{"kind": "decision", "command": "", "reason": f"Choose heightened or learning review depth, then record the review section or risk assess result with `reviewworthy packet review record --packet {quoted_packet} --input FILE --json`."}]
    if stage == "implementation":
        repository = packet.get("repository") if isinstance(packet.get("repository"), dict) else {}
        base = repository.get("default_branch") if isinstance(repository.get("default_branch"), str) and repository.get("default_branch") else "main"
        command = (
            f"reviewworthy diff bind --root . --packet {quoted_packet} "
            f"--base {shlex.quote(base)} --head HEAD --json"
        )
        return [{"kind": "command", "command": command, "reason": "Bind the current clean merge-base Diff after completing the approved implementation."}]
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
        receipt_errors = [error for error in validate_packet(packet)["errors"]
                          if error["path"].startswith("verification.receipts[")]
        planned_ids = {check.get("id") for check in checks if isinstance(check, dict)}
        recovery_ids = []
        for index, receipt in enumerate(verification.get("receipts", [])):
            if not isinstance(receipt, dict) or receipt.get("check_id") not in planned_ids:
                continue
            prefix = f"verification.receipts[{index}]"
            if (receipt.get("integrity_status") != "stable"
                    or any(error["path"].startswith(prefix) for error in receipt_errors)):
                if receipt["check_id"] not in missing_ids and receipt["check_id"] not in recovery_ids:
                    recovery_ids.append(receipt["check_id"])
        if missing_ids or recovery_ids:
            return [
                {
                    "kind": "command",
                    "command": f"reviewworthy verify run --root . --packet {quoted_packet} --check-id {shlex.quote(check_id)} --json",
                    "reason": (f"Restore a clean worktree at the bound HEAD (rebind a changed Diff), then rerun blocking check {check_id}."
                               if check_id in recovery_ids else f"Run required current check {check_id}."),
                }
                for check_id in [*missing_ids, *recovery_ids]
            ]
        return [{"kind": "decision", "command": "", "reason": f"Define at least one required verification-plan check, then record the plan with `reviewworthy packet verification plan --packet {quoted_packet} --input FILE --json`."}]
    if stage == "ownership":
        return [{"kind": "decision", "command": "", "reason": f"Complete the light Ownership Check, then record its explicit outcome and problem/scope/verification/risks with `reviewworthy packet ownership record --packet {quoted_packet} --input FILE --json`."}]
    if stage == "understanding":
        return [{"kind": "command", "command": f"reviewworthy understanding validate {quoted_packet} --json", "reason": "Inspect the Heightened/Learning understanding gaps, then record current Orientation and Assessment."}]
    if stage == "narrative":
        codes = {error["code"] for error in readiness_blockers(packet)}
        if codes & {"missing_ai_disclosure", "missing_disclosure_location", "missing_disclosure_stage", "disclosure_overclaims_verification"}:
            return [{"kind": "decision", "command": "", "reason": f"Record explicit assistance and disclosure claims with `reviewworthy packet ai record --packet {quoted_packet} --input FILE --json`."}]
        if codes & {"missing_pr_title", "missing_pr_body", "missing_human_expression", "disclosure_not_in_pr_body"}:
            return [{"kind": "decision", "command": "", "reason": f"Finish current prose and human expression, then use `reviewworthy packet narrative record --packet {quoted_packet} --title TITLE --body-file FILE --json` (add --human-expression-file FILE when required)."}]
        return [{"kind": "command", "command": f"reviewworthy packet narrative preview --packet {quoted_packet} --json",
                 "reason": f"Review the exact current prose/disclosure, then explicitly approve it with `reviewworthy packet narrative confirm --packet {quoted_packet} --human-confirmed --json`."}]

    if stage == "invalid":
        return [{"kind": "command", "command": f"reviewworthy packet validate {quoted_packet} --json", "reason": "Repair the current Packet 0.3 structure before continuing."}]
    if stage == "blocked":
        return [{"kind": "decision", "command": "", "reason": "Resolve the remaining policy, security, or hard-stop findings before continuing."}]
    recovery = _current_operation_recovery(packet, packet_path)
    if recovery:
        return [recovery]
    return [{"kind": "decision", "command": "", "reason": (
        "The Packet is ready. Choose the actual PR base/head refs and export the exact Body "
        f"with `reviewworthy packet narrative preview --packet {quoted_packet} --output FILE --json`, "
        "then use `reviewworthy remote plan --root ROOT --packet PACKET --repo OWNER/REPO "
        "--kind pull_request --title TITLE --body-file FILE --base BASE --head HEAD --json`. "
        "Use the Packet repository and confirmed title; approve the displayed operation ID before any write."
    )}]


def _current_operation_recovery(packet: dict[str, Any], packet_path: Path) -> dict[str, str] | None:
    """Suggest recovery only for an exact current operation; never change readiness."""

    directory = packet_path.parent / "local" / "v0.3" / "operations"
    for path in sorted(directory.glob("*.json")):
        try:
            operation, record = load_operation_state(path)
            if (operation.kind != "pull_request" or operation.purpose != "contribution"
                    or not repository_matches(packet.get("repository"), operation.repo)
                    or record["status"] not in {"pending", "pr_created", "link_attempted", "needs_reconciliation"}):
                continue
            current = build_operation(packet, operation.repo, "pull_request",
                                      packet["narrative"]["title"], packet["narrative"]["body"],
                                      operation.base, operation.head, packet["diff"])
            if current.as_dict() != operation.as_dict():
                continue
        except (GhError, OSError, ValueError):
            continue
        return {"kind": "command", "command": f"reviewworthy remote reconcile --state {shlex.quote(str(path))} --json",
                "reason": "Inspect the matching saved operation before any new write; an absent Issue backlink needs explicit confirmation of its original operation ID."}
    return None


def workflow_status(packet: Any, packet_path: Path) -> dict[str, Any]:
    validation = validate_packet(packet)
    validation_errors = list(validation.get("errors", []))
    readiness = readiness_blockers(packet)
    blockers = _deduplicated([*validation_errors, *readiness])
    structural_errors = [
        item for item in validation_errors
        if item.get("code") not in _EXPECTED_INCOMPLETE_CODES
        and not (item.get("code") == "invalid_repository_identity"
                 and item.get("path") in {"repository.owner", "repository.name"}
                 and isinstance(packet, dict) and isinstance(packet.get("repository"), dict)
                 and packet["repository"].get("owner") == packet["repository"].get("name") == "")
    ]
    if structural_errors or not isinstance(packet, dict):
        stage = "invalid"
    elif not blockers:
        stage = "ready"
    elif _has_hard_stop(packet, blockers):
        stage = "blocked"
    else:
        stage = _derived_stage(packet, blockers)
    return {
        "status_version": "0.3",
        "packet": str(packet_path),
        "current_stage": stage,
        "ready": not blockers,
        "blocking": blockers,
        "next": _next_actions(packet if isinstance(packet, dict) else {}, packet_path, stage),
    }
