"""Small, provider-free fixture evaluations for workflow boundary regressions."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from .action import check_evidence
from .candidate import validate_candidate_menu
from .contract import contract_snapshot
from .git import verification_plan_digest
from .packet import REQUIRED_NODES, semantic_snapshot, readiness_blockers, skeleton_packet
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
    packet["repository"] = {
        "provider": "github",
        "host": "github.com",
        "owner": "example",
        "name": "project",
        "repository_id": 101,
        "default_branch": "main",
        "base_sha": "base-sha",
    }
    packet["entry"]["source"] = "https://github.com/example/project/issues/1"
    packet["basis"] = {
        "kind": "issue",
        "references": ["https://github.com/example/project/issues/1"],
        "evidence": [],
        "labels": [],
        "verification": {
            "status": "verified",
            "provider": "github",
            "reference": "https://github.com/example/project/issues/1",
            "repository": "example/project",
            "repository_id": 101,
            "record_type": "issue",
            "host": "github.com",
            "number": 1,
            "url": "https://github.com/example/project/issues/1",
            "visibility": "public",
            "verified_at": "2026-08-07T00:00:00Z",
        },
    }
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
    packet["review"] = {"profile": "standard", "signals": [], "hard_stops": []}
    packet["ai_assistance"] = {
        "used": True,
        "stages": [
            {"name": "implementation", "level": "assisted", "human_verified": True},
            {"name": "verification", "level": "reviewed", "human_verified": True},
        ],
        "disclosure": {"text": "AI assistance was reviewed by the contributor.", "locations": ["pr_body"], "human_confirmed": True},
    }
    packet["diff"] = {
        "comparison": "merge_base",
        "base_tip_sha": "base-sha",
        "merge_base_sha": "merge-base-sha",
        "head_sha": "head-sha",
        "subject_digest": "subject-digest",
        "fingerprint_algorithm": "git-raw-content-v1",
        "changed_files": ["src/example.py"],
        "additions": 3,
        "deletions": 1,
    }
    packet["verification"] = {
        "plan": {
            "plan_version": "0.1",
            "checks": [{"id": "unit", "argv": ["python", "-m", "unittest"], "cwd": ".", "required": True}],
        },
        "receipts": [{
            "receipt_version": "0.3",
            "check_id": "unit",
            "plan_digest": "",
            "subject_digest": "subject-digest",
            "argv": ["python", "-m", "unittest"],
            "cwd": ".",
            "exit_code": 0,
            "command_outcome": "passed",
            "integrity_status": "stable",
            "head_sha": "head-sha",
            "head_sha_before": "head-sha",
            "head_sha_after": "head-sha",
            "worktree_clean_before": True,
            "worktree_clean_after": True,
            "stdout_sha256": "stdout-sha256",
            "stderr_sha256": "stderr-sha256",
            "provenance": "contributor_local",
        }],
    }
    packet["verification"]["plan_digest"] = verification_plan_digest(packet["verification"]["plan"])
    packet["verification"]["receipts"][0]["plan_digest"] = packet["verification"]["plan_digest"]
    packet["ownership"] = {
        "status": "passed",
        "problem": "The contributor can explain the failure.",
        "scope": "Only the input boundary changes.",
        "verification": "The focused unit check covers the boundary.",
        "risks": ["Existing callers may rely on the old exception path."],
    }
    packet["results"] = [{"node": node, "status": "passed", "evidence": [f"{node} recorded"]} for node in REQUIRED_NODES]
    packet["understanding"] = {
        "orientation": {
            "status": "passed",
            "summary": "The contract and evidence were explained.",
            "topics": ["contract", "diff", "verification", "policy"],
            "rubric": {
                "covered": ["behavior", "invariant", "test", "flow", "tradeoffs", "failures", "regressions"],
                "evidence": {
                    "behavior": "The boundary rejects the invalid input.",
                    "invariant": "Existing callers retain their behavior.",
                    "test": "The focused regression test exercises the boundary.",
                    "flow": "The input flows through the existing validation boundary.",
                    "tradeoffs": "A narrow guard avoids a larger caller refactor.",
                    "failures": "Invalid input is rejected before the old failure path.",
                    "regressions": "The focused test protects the existing caller contract.",
                },
            },
            "evidence": ["Orientation covered the material snapshot."],
        },
        "assessment": {
            "status": "passed",
            "questions": ["What boundary protects the invariant?"],
            "answers": ["The existing input boundary validates before the old path runs."],
            "rubric": {
                "covered": ["behavior", "invariant", "test", "flow", "tradeoffs", "failures", "regressions"],
                "evidence": {
                    "behavior": "The invalid input follows the guarded path.",
                    "invariant": "The existing caller contract remains unchanged.",
                    "test": "The regression command covers the changed path.",
                    "flow": "The answer traces the input through the guard.",
                    "tradeoffs": "It explains why the caller was not refactored.",
                    "failures": "It identifies the prior exception path.",
                    "regressions": "It identifies the protected caller behavior.",
                },
            },
            "evidence": ["The contributor answered a non-repeating question."],
        },
    }
    packet["narrative"] = {
        "title": "Fix invalid input handling",
        "body": "https://github.com/example/project/issues/1\n\n## Why\nFixes the reported regression.\n\n## Testing\n`python -m unittest`",
        "final_preview_confirmed": True,
        "human_expression_required": False,
        "human_expression": "",
    }
    packet["contract"]["approval"] = {"status": "approved", "human_confirmed": True}
    packet["contract"]["approval"]["contract_sha256"] = contract_snapshot(packet["contract"])
    snapshot = semantic_snapshot(packet)
    packet["snapshots"]["semantic"] = snapshot
    packet["understanding"]["orientation"]["semantic_snapshot"] = snapshot
    packet["understanding"]["assessment"]["semantic_snapshot"] = snapshot
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
            if expected.get("readiness_blocker"):
                packet = _base_packet()
                packet["policy"]["authoritative_claims"]["ai_assistance"] = actual["authoritative_claims"]["ai_assistance"]
                packet["snapshots"]["semantic"] = semantic_snapshot(packet)
                packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
                blocker_codes = {item["code"] for item in readiness_blockers(packet)}
                checks.append(("readiness_blocker", expected["readiness_blocker"] in blocker_codes, True))
        elif kind == "candidate":
            actual = validate_candidate_menu(fixture["menu"])
            candidate_id = fixture["menu"]["candidates"][0]["id"]
            checks = [("valid", actual["valid"], expected.get("valid")), ("recommendation", fixture["menu"]["candidates"][0]["recommendation"], expected.get("recommendation")), ("candidate_id", candidate_id, expected.get("candidate_id", candidate_id))]
        elif kind == "packet":
            packet = _base_packet()
            for mutation in fixture.get("mutations", []):
                _set_path(packet, mutation["path"], mutation["value"])
            if fixture.get("refresh_semantics", True):
                snapshot = semantic_snapshot(packet)
                packet["snapshots"]["semantic"] = snapshot
                packet["understanding"]["orientation"]["semantic_snapshot"] = snapshot
                packet["understanding"]["assessment"]["semantic_snapshot"] = snapshot
            actual = {"blocker_codes": sorted({item["code"] for item in readiness_blockers(packet)})}
            if not isinstance(expected.get("blocker_codes"), list) or not isinstance(expected.get("result"), str):
                raise ValueError("packet evals must assert exact blocker_codes and result")
            actual["result"] = "blocked" if actual["blocker_codes"] else "ready"
            checks = [
                ("result", actual["result"], expected["result"]),
                ("blocker_codes", actual["blocker_codes"], sorted(expected["blocker_codes"])),
            ]
        elif kind == "risk":
            actual = assess_manifest(fixture["manifest"])
            checks = [("hard_stop", actual["hard_stops"][0]["code"] if actual["hard_stops"] else None, expected.get("hard_stop")), ("review_profile", actual["review_profile"], expected.get("review_profile", actual["review_profile"]))]
        elif kind == "action":
            event = fixture.get("event", {})
            if not isinstance(event, dict):
                raise ValueError("action eval event must be an object")
            if not isinstance(expected.get("violation_codes"), list) or not isinstance(expected.get("conclusion"), str) or not isinstance(expected.get("result"), str):
                raise ValueError("action evals must assert exact violation_codes, conclusion, and result")
            with tempfile.TemporaryDirectory() as directory:
                actual = check_evidence(
                    fixture.get("body", ""),
                    root=Path(directory),
                    event_name=event.get("name"),
                    event_repository=event.get("repository"),
                    event_repository_id=event.get("repository_id"),
                    event_base_sha=event.get("base_sha"),
                    event_head_sha=event.get("head_sha"),
                    mode=fixture.get("mode", "report"),
                )
            actual_result = "failed" if actual["conclusion"] == "failure" else "passed"
            checks = [
                ("violation_codes", sorted(item["code"] for item in actual["violations"]), sorted(expected["violation_codes"])),
                ("conclusion", actual["conclusion"], expected["conclusion"]),
                ("result", actual_result, expected["result"]),
            ]
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
    if path.is_file():
        paths = [path]
    elif path.is_dir():
        paths = sorted(path.glob("*.json"))
    else:
        paths = []
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
