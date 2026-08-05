"""Small, provider-free fixture evaluations for workflow boundary regressions."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from .action import check_packet
from .candidate import validate_candidate_menu
from .packet import REQUIRED_NODES, material_snapshot, readiness_blockers, skeleton_packet
from .policy import inspect_policy
from .risk import assess_manifest


def _set_path(value: Any, path: str, replacement: Any) -> None:
    parts = path.split(".")
    current = value
    for part in parts[:-1]:
        if isinstance(current, list):
            current = current[int(part)]
        else:
            if part not in current or not isinstance(current[part], (dict, list)):
                current[part] = {}
            current = current[part]
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = replacement
    else:
        current[last] = replacement


def _get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _base_packet() -> dict[str, Any]:
    packet = skeleton_packet("eval-001", "issue-backed")
    packet["entry"]["source"] = "https://github.com/example/project/issues/1"
    packet["basis"] = {"kind": "issue", "references": ["https://github.com/example/project/issues/1"], "evidence": [], "labels": []}
    packet["contract"].update(
        {
            "problem": "A reproducible failure needs a narrow fix.",
            "non_goals": ["No unrelated refactor"],
            "scope": {"files": ["src/example.py"], "modules": ["input boundary"]},
            "invariants": ["Existing callers keep their behavior."],
            "design": "Guard the invalid input at the existing boundary.",
            "alternatives": [{"option": "Refactor the caller", "rejected_because": "Larger review surface."}],
            "validation_plan": ["Run the focused unit test."],
            "risks": ["A caller may rely on the old exception path."],
            "success_criteria": ["The regression test passes."],
            "max_diff_lines": 20,
        }
    )
    packet["policy"] = {
        "authoritative_claims": {
            "ai_assistance": "allowed",
            "issue_required": False,
            "disclosure_required": False,
            "human_pr_narrative_required": False,
            "good_first_issue_ai_allowed": True,
        },
        "conflicts": [],
        "posture": "explicit",
    }
    packet["review"] = {"depth": "standard", "signals": [], "hard_stops": []}
    packet["ai_assistance"] = {
        "used": True,
        "stages": [
            {"name": "implementation", "level": "assisted", "human_verified": True},
            {"name": "verification", "level": "reviewed", "human_verified": True},
        ],
        "disclosure": {"text": "AI assistance was reviewed by the contributor.", "locations": ["pr_body"], "human_confirmed": True},
    }
    packet["diff"] = {"changed_files": ["src/example.py"], "additions": 3, "deletions": 1}
    packet["verification"] = {"commands": ["python -m unittest"], "evidence": ["exit 0"]}
    packet["results"] = [{"node": node, "status": "passed", "evidence": [f"{node} recorded"]} for node in REQUIRED_NODES]
    packet["understanding"] = {
        "orientation": {"status": "passed", "summary": "The contract and evidence were explained."},
        "assessment": {
            "status": "passed",
            "questions": ["What boundary protects the invariant?"],
            "answers": ["The existing input boundary validates before the old path runs."],
        },
    }
    packet["narrative"] = {
        "title": "Fix invalid input handling",
        "body": "## Why\nFixes the reported regression.\n\n## Testing\n`python -m unittest`",
        "final_preview_confirmed": True,
        "human_expression_required": False,
        "human_expression": "",
    }
    packet["materials"]["material_snapshot"] = material_snapshot(packet)
    packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
    return packet


def _assert_equal(actual: Any, expected: Any, path: str) -> tuple[bool, str]:
    if actual == expected:
        return True, ""
    return False, f"{path}: expected {expected!r}, got {actual!r}"


def _run_case(path: Path, fixture: dict[str, Any]) -> dict[str, Any]:
    case_id = str(fixture.get("id") or path.stem)
    try:
        kind = fixture.get("kind")
        expected = fixture.get("assert", {})
        if kind == "policy":
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative, content in fixture.get("files", {}).items():
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(str(content), encoding="utf-8")
                actual = inspect_policy(root)
            checks = [("authoritative_claims.ai_assistance", _get_path(actual, "authoritative_claims.ai_assistance"), expected.get("ai_assistance"))]
        elif kind == "candidate":
            actual = validate_candidate_menu(fixture["menu"])
            candidate_id = fixture["menu"]["candidates"][0]["id"]
            checks = [("valid", actual["valid"], expected.get("valid")), ("recommendation", fixture["menu"]["candidates"][0]["recommendation"], expected.get("recommendation")), ("candidate_id", candidate_id, expected.get("candidate_id", candidate_id))]
        elif kind == "packet":
            packet = _base_packet()
            for mutation in fixture.get("mutations", []):
                _set_path(packet, mutation["path"], mutation["value"])
            if fixture.get("refresh_materials", True):
                packet["materials"]["material_snapshot"] = material_snapshot(packet)
                packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            actual = {"blocker_codes": sorted({item["code"] for item in readiness_blockers(packet)})}
            checks = [("blocker", expected.get("blocker") in actual["blocker_codes"], True)]
        elif kind == "action":
            packet = _base_packet()
            for mutation in fixture.get("mutations", []):
                _set_path(packet, mutation["path"], mutation["value"])
            with tempfile.TemporaryDirectory() as directory:
                packet_path = Path(directory) / "packet.json"
                packet_path.write_text(json.dumps(packet), encoding="utf-8")
                actual = check_packet(packet_path, fixture.get("changed_files"))
            checks = [("conclusion", actual["conclusion"], expected.get("conclusion")), ("violation", actual["violations"][0]["code"] if actual["violations"] else None, expected.get("violation"))]
        elif kind == "risk":
            actual = assess_manifest(fixture["manifest"])
            checks = [("hard_stop", actual["hard_stops"][0]["code"] if actual["hard_stops"] else None, expected.get("hard_stop")), ("review_depth", actual["review_depth"], expected.get("review_depth", actual["review_depth"]))]
        else:
            raise ValueError(f"Unsupported fixture kind: {kind}")

        failures: list[str] = []
        for check_path, actual_value, expected_value in checks:
            passed, message = _assert_equal(actual_value, expected_value, check_path)
            if not passed:
                failures.append(message)
        return {"id": case_id, "result": "passed" if not failures else "failed", "failures": failures}
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        return {"id": case_id, "result": "failed", "failures": [str(exc)]}


def run_evals(path: Path) -> dict[str, Any]:
    paths = [path] if path.is_file() else sorted(path.glob("*.json")) if path.is_dir() else []
    if not paths:
        return {"result": "failed", "total": 0, "passed": 0, "failed": 0, "cases": [], "error": f"No eval fixtures found at {path}"}
    cases: list[dict[str, Any]] = []
    for fixture_path in paths:
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            if not isinstance(fixture, dict):
                raise ValueError("Fixture must be a JSON object")
            cases.append(_run_case(fixture_path, fixture))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            cases.append({"id": fixture_path.stem, "result": "failed", "failures": [str(exc)]})
    passed = sum(case["result"] == "passed" for case in cases)
    return {
        "result": "passed" if passed == len(cases) else "failed",
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
    }
