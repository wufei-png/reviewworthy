"""Structured, material-bound Orientation and Assessment records."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


UNDERSTANDING_STATUSES = {"passed", "failed", "blocked", "unknown", "not_run"}
ORIENTATION_TOPICS = {"contract", "diff", "verification", "policy"}
RUBRIC_CATEGORIES = {"behavior", "invariant", "test", "flow", "tradeoffs", "failures", "regressions"}
RUBRIC_BY_PROFILE = {
    "standard": {"behavior", "invariant", "test"},
    "heightened": {"behavior", "invariant", "test", "flow", "tradeoffs", "failures", "regressions"},
    "learning": {"behavior", "invariant", "test", "flow", "tradeoffs", "failures", "regressions"},
}


def _error(errors: list[dict[str, str]], code: str, message: str, path: str) -> None:
    errors.append({"code": code, "message": message, "path": path})


def _validate_rubric(record: dict[str, Any], profile: str, path: str, status: str, errors: list[dict[str, str]]) -> None:
    rubric = record.get("rubric")
    if not isinstance(rubric, dict):
        _error(errors, "invalid_understanding_rubric", "Understanding rubric must be an object", path)
        return
    covered = rubric.get("covered", [])
    evidence = rubric.get("evidence", {})
    if not isinstance(covered, list) or not all(isinstance(item, str) for item in covered):
        _error(errors, "invalid_rubric_categories", "Rubric covered must be a list of category strings", f"{path}.covered")
        covered = []
    unknown = sorted(set(covered) - RUBRIC_CATEGORIES)
    if unknown:
        _error(errors, "unknown_rubric_category", f"Unsupported rubric category(s): {unknown}", f"{path}.covered")
    if not isinstance(evidence, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in evidence.items()):
        _error(errors, "invalid_rubric_evidence", "Rubric evidence must map category names to strings", f"{path}.evidence")
        evidence = {}
    if status == "passed":
        required = RUBRIC_BY_PROFILE.get(profile, RUBRIC_BY_PROFILE["standard"])
        missing = sorted(required - set(covered))
        if missing:
            _error(errors, "missing_rubric_categories", f"Understanding must cover rubric categories: {missing}", f"{path}.covered")
        empty = sorted(category for category in required if not str(evidence.get(category, "")).strip())
        if empty:
            _error(errors, "missing_rubric_evidence", f"Understanding rubric needs evidence for: {empty}", f"{path}.evidence")


def validate_understanding(understanding: Any, expected_snapshot: str, *, review_profile: str = "standard") -> dict[str, Any]:
    """Validate both understanding phases against the current semantic snapshot."""

    errors: list[dict[str, str]] = []
    if not isinstance(understanding, dict):
        _error(errors, "invalid_understanding", "understanding must be an object", "understanding")
        return {"valid": False, "errors": errors}
    for key in sorted(set(understanding) - {"orientation", "assessment"}):
        _error(errors, "unknown_understanding_field", f"understanding.{key} is not part of the current format", f"understanding.{key}")

    orientation = understanding.get("orientation")
    if not isinstance(orientation, dict):
        _error(errors, "invalid_orientation", "understanding.orientation must be an object", "understanding.orientation")
    else:
        allowed_orientation = {"status", "summary", "topics", "evidence", "rubric", "semantic_snapshot"}
        for key in sorted(set(orientation) - allowed_orientation):
            _error(errors, "unknown_orientation_field", f"understanding.orientation.{key} is not part of the current format", f"understanding.orientation.{key}")
        status = orientation.get("status")
        if status not in UNDERSTANDING_STATUSES:
            _error(errors, "invalid_orientation", "understanding.orientation.status is required", "understanding.orientation.status")
        summary = orientation.get("summary")
        if not isinstance(summary, str):
            _error(errors, "invalid_orientation_summary", "Orientation summary must be a string", "understanding.orientation.summary")
        topics = orientation.get("topics")
        if not isinstance(topics, list) or not all(isinstance(item, str) for item in topics):
            _error(errors, "invalid_orientation_topics", "Orientation topics must be a list of strings", "understanding.orientation.topics")
        evidence = orientation.get("evidence")
        if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
            _error(errors, "invalid_orientation_evidence", "Orientation evidence must be a list of strings", "understanding.orientation.evidence")
        if not isinstance(orientation.get("semantic_snapshot"), str) or not orientation["semantic_snapshot"].strip():
            _error(errors, "invalid_orientation_snapshot", "Orientation semantic_snapshot must be a non-empty string", "understanding.orientation.semantic_snapshot")
        _validate_rubric(orientation, review_profile, "understanding.orientation.rubric", status, errors)
        if status == "passed":
            if not isinstance(orientation.get("summary"), str) or not orientation["summary"].strip():
                _error(errors, "missing_orientation_summary", "A passed Orientation needs a non-empty summary", "understanding.orientation.summary")
            if isinstance(topics, list) and not ORIENTATION_TOPICS.issubset(set(topics)):
                _error(errors, "missing_orientation_topics", "Orientation must cover contract, diff, verification, and policy", "understanding.orientation.topics")
            if orientation.get("semantic_snapshot") != expected_snapshot:
                _error(errors, "stale_orientation", "Orientation is not bound to the current semantic snapshot", "understanding.orientation.semantic_snapshot")

    assessment = understanding.get("assessment")
    if not isinstance(assessment, dict):
        _error(errors, "invalid_assessment", "understanding.assessment must be an object", "understanding.assessment")
    else:
        allowed_assessment = {"status", "questions", "answers", "evidence", "rubric", "semantic_snapshot"}
        for key in sorted(set(assessment) - allowed_assessment):
            _error(errors, "unknown_assessment_field", f"understanding.assessment.{key} is not part of the current format", f"understanding.assessment.{key}")
        status = assessment.get("status")
        if status not in UNDERSTANDING_STATUSES:
            _error(errors, "invalid_assessment", "understanding.assessment.status is required", "understanding.assessment.status")
        questions = assessment.get("questions")
        answers = assessment.get("answers")
        if not isinstance(questions, list) or not all(isinstance(item, str) and item.strip() for item in questions):
            _error(errors, "invalid_assessment_questions", "Assessment questions must be non-empty strings", "understanding.assessment.questions")
        elif status == "passed" and not questions:
            _error(errors, "missing_assessment_questions", "Assessment needs at least one question", "understanding.assessment.questions")
        if not isinstance(answers, list) or not all(isinstance(item, str) for item in answers):
            _error(errors, "invalid_assessment_answers", "Assessment answers must be strings", "understanding.assessment.answers")
        elif isinstance(questions, list) and (status == "passed" or questions or answers) and len(answers) != len(questions):
            _error(errors, "assessment_answer_mismatch", "Assessment answers must match the question count", "understanding.assessment.answers")
        evidence = assessment.get("evidence")
        if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
            _error(errors, "invalid_assessment_evidence", "Assessment evidence must be a list of strings", "understanding.assessment.evidence")
        if not isinstance(assessment.get("semantic_snapshot"), str) or not assessment["semantic_snapshot"].strip():
            _error(errors, "invalid_assessment_snapshot", "Assessment semantic_snapshot must be a non-empty string", "understanding.assessment.semantic_snapshot")
        _validate_rubric(assessment, review_profile, "understanding.assessment.rubric", status, errors)
        if status == "passed":
            if isinstance(answers, list) and any(not answer.strip() for answer in answers if isinstance(answer, str)):
                _error(errors, "empty_assessment_answer", "A passed Assessment needs a human answer for every question", "understanding.assessment.answers")
            if assessment.get("semantic_snapshot") != expected_snapshot:
                _error(errors, "stale_assessment", "Assessment is not bound to the current semantic snapshot", "understanding.assessment.semantic_snapshot")
            if not isinstance(orientation, dict) or orientation.get("status") != "passed":
                _error(errors, "assessment_requires_orientation", "A passed Assessment requires a passed Orientation", "understanding.orientation.status")
            elif orientation.get("semantic_snapshot") != expected_snapshot:
                _error(errors, "assessment_requires_current_orientation", "A passed Assessment requires a current Orientation", "understanding.orientation.semantic_snapshot")

    return {"valid": not errors, "errors": errors, "semantic_snapshot": expected_snapshot}


def record_understanding(
    packet: dict[str, Any],
    phase: str,
    status: str,
    semantic_snapshot: str,
    *,
    summary: str = "",
    topics: list[str] | None = None,
    evidence: list[str] | None = None,
    questions: list[str] | None = None,
    answers: list[str] | None = None,
    rubric: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record one phase while preserving a prior phase's material binding."""

    if phase not in {"orientation", "assessment"}:
        raise ValueError("phase must be orientation or assessment")
    if status not in UNDERSTANDING_STATUSES:
        raise ValueError(f"status must be one of {sorted(UNDERSTANDING_STATUSES)}")
    updated = deepcopy(packet)
    understanding = updated.setdefault("understanding", {})
    if not isinstance(understanding, dict):
        raise ValueError("packet.understanding must be an object")
    if phase == "assessment":
        orientation = understanding.get("orientation")
        if (
            not isinstance(orientation, dict)
            or orientation.get("status") != "passed"
            or orientation.get("semantic_snapshot") != semantic_snapshot
        ):
            raise ValueError("Assessment requires a passed Orientation bound to the current semantic snapshot")
    if phase == "orientation":
        understanding["orientation"] = {
            "status": status,
            "summary": summary,
            "topics": list(topics or []),
            "evidence": list(evidence or []),
            "rubric": {"covered": sorted(rubric or {}), "evidence": dict(rubric or {})},
            "semantic_snapshot": semantic_snapshot,
        }
    else:
        understanding["assessment"] = {
            "status": status,
            "questions": list(questions or []),
            "answers": list(answers or []),
            "evidence": list(evidence or []),
            "rubric": {"covered": sorted(rubric or {}), "evidence": dict(rubric or {})},
            "semantic_snapshot": semantic_snapshot,
        }
    return updated
