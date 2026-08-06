"""Contribution Packet validation and understanding-material freshness."""

from __future__ import annotations

from typing import Any

from .contract import CONTRACT_FIELDS, CONTRACT_VERSION
from .disclosure import ASSISTANCE_LEVELS, DISCLOSURE_STAGES, disclosure_errors
from .signal import signal_readiness_blockers, skeleton_signal, validate_basis_signal
from .util import sha256_json


REQUIRED_NODES = (
    "policy_check",
    "contribution_basis",
    "contribution_contract",
    "implementation",
    "verification",
    "understanding",
    "narrative",
)
ALLOWED_STATUSES = {"passed", "failed", "blocked", "unknown", "not_run"}


def material_snapshot(packet: dict[str, Any]) -> str:
    """Hash only the materials Orientation and Assessment are about."""

    return sha256_json(
        {
            "contract": packet.get("contract", {}),
            "diff": packet.get("diff", {}),
            "verification": packet.get("verification", {}),
            "policy": packet.get("policy", {}),
        }
    )


def result_record(
    node: str,
    status: str,
    evidence: list[str] | None = None,
    details: dict[str, Any] | None = None,
    material_snapshot_value: str | None = None,
) -> dict[str, Any]:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported result status: {status}")
    record: dict[str, Any] = {
        "node": node,
        "status": status,
        "evidence": evidence or [],
        "details": details or {},
    }
    if material_snapshot_value:
        record["material_snapshot"] = material_snapshot_value
    return record


def skeleton_packet(contribution_id: str, mode: str) -> dict[str, Any]:
    """Create an explicit, incomplete packet for a new contribution."""

    if mode not in {"issue-backed", "discovery"}:
        raise ValueError("mode must be issue-backed or discovery")
    packet: dict[str, Any] = {
        "packet_version": "0.1",
        "contribution_id": contribution_id,
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
        "review": {"depth": "standard", "signals": [], "hard_stops": []},
        "ai_assistance": {
            "used": True,
            "stages": [],
            "disclosure": {"text": "", "locations": [], "human_confirmed": False},
        },
        "diff": {"changed_files": [], "additions": 0, "deletions": 0},
        "verification": {"commands": [], "evidence": []},
        "materials": {},
        "results": [result_record(node, "not_run") for node in REQUIRED_NODES],
        "understanding": {
            "orientation": {"status": "not_run", "summary": "", "material_snapshot": ""},
            "assessment": {"status": "not_run", "questions": [], "answers": []},
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
        packet["basis"]["signal"] = skeleton_signal("reproducible-evidence")
    packet["materials"]["material_snapshot"] = material_snapshot(packet)
    packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
    packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
    return packet


def _error(errors: list[dict[str, str]], code: str, message: str, path: str) -> None:
    errors.append({"code": code, "message": message, "path": path})


def validate_packet(packet: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    required_top = (
        "packet_version",
        "contribution_id",
        "entry",
        "basis",
        "contract",
        "policy",
        "review",
        "ai_assistance",
        "diff",
        "verification",
        "materials",
        "results",
        "understanding",
        "narrative",
    )
    for key in required_top:
        if key not in packet:
            _error(errors, "missing_field", f"Required field is missing: {key}", key)

    if packet.get("packet_version") != "0.1":
        _error(errors, "unsupported_version", "packet_version must be 0.1", "packet_version")
    if not isinstance(packet.get("contribution_id"), str) or not packet.get("contribution_id"):
        _error(errors, "invalid_contribution_id", "contribution_id must be a non-empty string", "contribution_id")

    entry = packet.get("entry", {})
    if not isinstance(entry, dict) or entry.get("mode") not in {"issue-backed", "discovery"}:
        _error(errors, "invalid_entry", "entry.mode must be issue-backed or discovery", "entry.mode")

    basis = packet.get("basis", {})
    if not isinstance(basis, dict) or basis.get("kind") not in {"issue", "signal", "discovery-evidence"}:
        _error(errors, "invalid_basis", "basis.kind must be issue, signal, or discovery-evidence", "basis.kind")
    elif not basis.get("references") and not basis.get("evidence"):
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
    if not isinstance(review, dict) or review.get("depth") not in {"standard", "heightened"}:
        _error(errors, "invalid_review_depth", "review.depth must be standard or heightened", "review.depth")
    if isinstance(review, dict) and not isinstance(review.get("hard_stops", []), list):
        _error(errors, "invalid_hard_stops", "review.hard_stops must be a list", "review.hard_stops")
    if isinstance(review, dict):
        if not isinstance(review.get("signals", []), list):
            _error(errors, "invalid_review_signals", "review.signals must be a list", "review.signals")
        elif review.get("signals") and review.get("depth") == "standard":
            _error(errors, "review_depth_too_low", "Risk signals require heightened review depth", "review.depth")

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
        changed_files = diff.get("changed_files", [])
        if not isinstance(changed_files, list):
            _error(errors, "invalid_changed_files", "diff.changed_files must be a list", "diff.changed_files")
        elif not all(isinstance(item, str) for item in changed_files):
            _error(errors, "invalid_changed_file", "diff.changed_files items must be strings", "diff.changed_files")
        for count_key in ("additions", "deletions"):
            if count_key in diff and (not isinstance(diff[count_key], int) or isinstance(diff[count_key], bool) or diff[count_key] < 0):
                _error(errors, "invalid_diff_count", f"diff.{count_key} must be a non-negative integer", f"diff.{count_key}")

    verification = packet.get("verification", {})
    if not isinstance(verification, dict):
        _error(errors, "invalid_verification", "verification must be an object", "verification")

    materials = packet.get("materials", {})
    if not isinstance(materials, dict):
        _error(errors, "invalid_materials", "materials must be an object", "materials")
    else:
        expected = material_snapshot(packet)
        if materials.get("material_snapshot") != expected:
            _error(
                errors,
                "material_snapshot_mismatch",
                "materials.material_snapshot does not match the current contract, Diff, verification, and policy",
                "materials.material_snapshot",
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

    understanding = packet.get("understanding", {})
    if not isinstance(understanding, dict):
        _error(errors, "invalid_understanding", "understanding must be an object", "understanding")
    else:
        orientation = understanding.get("orientation", {})
        assessment = understanding.get("assessment", {})
        if not isinstance(orientation, dict) or orientation.get("status") not in ALLOWED_STATUSES:
            _error(errors, "invalid_orientation", "understanding.orientation.status is required", "understanding.orientation")
        if not isinstance(assessment, dict) or assessment.get("status") not in ALLOWED_STATUSES:
            _error(errors, "invalid_assessment", "understanding.assessment.status is required", "understanding.assessment")
        if isinstance(assessment, dict):
            expected = material_snapshot(packet)
            if assessment.get("material_snapshot") != expected:
                _error(errors, "stale_assessment", "Assessment is not bound to the current material snapshot", "understanding.assessment.material_snapshot")
            questions = assessment.get("questions", [])
            answers = assessment.get("answers", [])
            if not isinstance(questions, list) or not questions:
                _error(errors, "missing_assessment_questions", "Assessment needs at least one question", "understanding.assessment.questions")
            if not isinstance(answers, list) or len(answers) != len(questions):
                _error(errors, "assessment_answer_mismatch", "Assessment answers must match the question count", "understanding.assessment.answers")

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
        if (narrative.get("human_expression_required") or (isinstance(review, dict) and review.get("depth") == "heightened")) and not str(narrative.get("human_expression", "")).strip():
            _error(errors, "missing_human_expression", "This contribution requires human-authored motivation/trade-offs/risk", "narrative.human_expression")

    return {"valid": not errors, "errors": errors, "result_nodes": sorted(result_by_node)}


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


def policy_violations(packet: dict[str, Any], *, enforce_disclosure: bool) -> list[dict[str, str]]:
    """Return only deterministic violations from known policy claims."""

    policy = packet.get("policy", {})
    if not isinstance(policy, dict):
        return []
    violations: list[dict[str, str]] = []
    if policy.get("conflicts"):
        violations.append({"code": "policy_conflict", "message": "Policy sources conflict.", "path": "policy.conflicts"})

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
    if claims.get("good_first_issue_ai_allowed") is False:
        labels = basis.get("labels", []) if isinstance(basis, dict) else []
        if any(str(label).lower() in {"good first issue", "good-first-issue"} for label in labels) and ai_used is not False:
            violations.append({"code": "good_first_issue_ai_disallowed", "message": "The repository does not allow AI-assisted work on good-first-issue items.", "path": "basis.labels"})
    return violations


def readiness_blockers(packet: dict[str, Any]) -> list[dict[str, str]]:
    validation = validate_packet(packet)
    blockers = list(validation["errors"])

    evidence_violations, _unknowns = deterministic_evidence_checks(packet, strict=True)
    blockers.extend(evidence_violations)

    entry = packet.get("entry", {})
    basis = packet.get("basis", {})
    review = packet.get("review", {})
    if isinstance(review, dict) and review.get("signals") and review.get("depth") != "heightened":
        blockers.append({"code": "review_depth_too_low", "message": "Risk signals require heightened review depth.", "path": "review.depth"})
    for stop in review.get("hard_stops", []) if isinstance(review, dict) and isinstance(review.get("hard_stops", []), list) else []:
        if isinstance(stop, dict):
            blockers.append({"code": "hard_stop", "message": str(stop.get("reason", stop)), "path": "review.hard_stops"})
        else:
            blockers.append({"code": "hard_stop", "message": str(stop), "path": "review.hard_stops"})

    policy = packet.get("policy", {})

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

    verification = packet.get("verification", {})
    if (
        not isinstance(verification, dict)
        or not isinstance(verification.get("commands"), list)
        or not verification.get("commands")
        or not isinstance(verification.get("evidence"), list)
        or not verification.get("evidence")
    ):
        blockers.append({"code": "missing_verification_evidence", "message": "Remote readiness requires verification commands and evidence.", "path": "verification"})

    blockers.extend(policy_violations(packet, enforce_disclosure=True))

    if isinstance(basis, dict):
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

    understanding = packet.get("understanding", {}) if isinstance(packet.get("understanding", {}), dict) else {}
    orientation = understanding.get("orientation", {})
    if not isinstance(orientation, dict) or orientation.get("status") != "passed":
        blockers.append({"code": "orientation_not_passed", "message": "Understanding Orientation must pass before Assessment and remote readiness.", "path": "understanding.orientation.status"})
    elif orientation.get("material_snapshot") != material_snapshot(packet):
        blockers.append({"code": "stale_orientation", "message": "Understanding Orientation is stale.", "path": "understanding.orientation.material_snapshot"})
    assessment = understanding.get("assessment", {})
    if assessment.get("status") != "passed":
        blockers.append({"code": "assessment_not_passed", "message": "Understanding Assessment has not passed.", "path": "understanding.assessment.status"})
    elif assessment.get("material_snapshot") != material_snapshot(packet):
        blockers.append({"code": "stale_assessment", "message": "Understanding Assessment is stale.", "path": "understanding.assessment.material_snapshot"})
    return blockers
