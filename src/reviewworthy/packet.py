"""Contribution Packet validation and understanding-material freshness."""

from __future__ import annotations

from typing import Any

from .disclosure import ASSISTANCE_LEVELS, DISCLOSURE_STAGES, disclosure_errors
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
            "orientation": {"status": "not_run", "summary": ""},
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
    packet["materials"]["material_snapshot"] = material_snapshot(packet)
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

    contract = packet.get("contract", {})
    if not isinstance(contract, dict):
        _error(errors, "invalid_contract", "contract must be an object", "contract")
    else:
        for key in ("problem", "non_goals", "scope", "invariants", "design", "validation_plan", "success_criteria"):
            if key not in contract:
                _error(errors, "missing_contract_field", f"Contribution contract field is missing: {key}", f"contract.{key}")
        if isinstance(contract.get("scope"), dict) and not isinstance(contract["scope"].get("files", []), list):
            _error(errors, "invalid_scope", "contract.scope.files must be a list", "contract.scope.files")

    review = packet.get("review", {})
    if not isinstance(review, dict) or review.get("depth") not in {"standard", "heightened"}:
        _error(errors, "invalid_review_depth", "review.depth must be standard or heightened", "review.depth")
    if isinstance(review, dict) and not isinstance(review.get("hard_stops", []), list):
        _error(errors, "invalid_hard_stops", "review.hard_stops must be a list", "review.hard_stops")

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
        disclosure = ai_assistance.get("disclosure")
        if disclosure is not None:
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
        if narrative.get("human_expression_required") and not str(narrative.get("human_expression", "")).strip():
            _error(errors, "missing_human_expression", "This contribution requires human-authored motivation/trade-offs/risk", "narrative.human_expression")

    return {"valid": not errors, "errors": errors, "result_nodes": sorted(result_by_node)}


def readiness_blockers(packet: dict[str, Any]) -> list[dict[str, str]]:
    validation = validate_packet(packet)
    blockers = list(validation["errors"])

    review = packet.get("review", {})
    for stop in review.get("hard_stops", []) if isinstance(review, dict) and isinstance(review.get("hard_stops", []), list) else []:
        if isinstance(stop, dict):
            blockers.append({"code": "hard_stop", "message": str(stop.get("reason", stop)), "path": "review.hard_stops"})
        else:
            blockers.append({"code": "hard_stop", "message": str(stop), "path": "review.hard_stops"})

    policy = packet.get("policy", {})
    if isinstance(policy, dict) and policy.get("conflicts"):
        blockers.append({"code": "policy_conflict", "message": "Policy sources conflict.", "path": "policy.conflicts"})

    for result in packet.get("results", []) if isinstance(packet.get("results", []), list) else []:
        if isinstance(result, dict) and result.get("status") != "passed":
            blockers.append(
                {
                    "code": "node_not_passed",
                    "message": f"Flow node {result.get('node', '<unknown>')} has status {result.get('status')}",
                    "path": "results",
                }
            )

    policy_claims = policy.get("authoritative_claims", {}) if isinstance(policy, dict) else {}
    if not isinstance(policy_claims, dict):
        policy_claims = {}
    policy_posture = policy.get("posture") if isinstance(policy, dict) else None
    if policy_posture not in {"explicit", "conservative"}:
        policy_posture = "conservative"
    narrative = packet.get("narrative", {})
    if not isinstance(narrative, dict):
        narrative = {}
    for disclosure_error in disclosure_errors(packet):
        blockers.append(disclosure_error)
    if policy_claims.get("ai_assistance") == "prohibited":
        ai_used = packet.get("ai_assistance", {}).get("used") if isinstance(packet.get("ai_assistance", {}), dict) else None
        if ai_used is not False:
            blockers.append({"code": "ai_assistance_prohibited", "message": "The repository policy prohibits AI assistance for this contribution.", "path": "ai_assistance.used"})
    if policy_claims.get("issue_required") is True:
        basis_kind = packet.get("basis", {}).get("kind") if isinstance(packet.get("basis", {}), dict) else None
        if basis_kind != "issue":
            blockers.append({"code": "issue_required", "message": "The repository policy requires an Issue-backed contribution.", "path": "basis.kind"})
    entry = packet.get("entry", {})
    basis = packet.get("basis", {})
    if policy_claims.get("discovery_evidence_allowed") is False and (
        (isinstance(entry, dict) and entry.get("mode") == "discovery")
        or (isinstance(basis, dict) and basis.get("kind") == "discovery-evidence")
    ):
        blockers.append({"code": "discovery_evidence_disallowed", "message": "Repository policy does not allow Discovery evidence as the contribution basis.", "path": "basis.kind"})
    if policy_claims.get("human_pr_narrative_required") is True and not str(narrative.get("human_expression", "")).strip():
        blockers.append({"code": "missing_human_expression", "message": "The repository policy requires human-owned PR motivation and trade-offs.", "path": "narrative.human_expression"})
    if policy_claims.get("good_first_issue_ai_allowed") is False:
        basis = packet.get("basis", {})
        labels = basis.get("labels", []) if isinstance(basis, dict) else []
        ai_assistance = packet.get("ai_assistance", {})
        if any(str(label).lower() in {"good first issue", "good-first-issue"} for label in labels) and isinstance(ai_assistance, dict) and ai_assistance.get("used") is not False:
            blockers.append({"code": "good_first_issue_ai_disallowed", "message": "The repository does not allow AI-assisted work on good-first-issue items.", "path": "basis.labels"})

    assessment = packet.get("understanding", {}).get("assessment", {}) if isinstance(packet.get("understanding", {}), dict) else {}
    if assessment.get("status") != "passed":
        blockers.append({"code": "assessment_not_passed", "message": "Understanding Assessment has not passed.", "path": "understanding.assessment.status"})
    elif assessment.get("material_snapshot") != material_snapshot(packet):
        blockers.append({"code": "stale_assessment", "message": "Understanding Assessment is stale.", "path": "understanding.assessment.material_snapshot"})
    return blockers
