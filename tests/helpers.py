from __future__ import annotations

from reviewworthy.contract import contract_snapshot
from reviewworthy.packet import REQUIRED_NODES, material_snapshot


def valid_packet() -> dict:
    packet = {
        "packet_version": "0.1",
        "contribution_id": "contrib-test-001",
        "repository": {
            "provider": "github",
            "host": "github.com",
            "owner": "example",
            "name": "project",
            "repository_id": 101,
            "default_branch": "main",
            "base_sha": "base-sha",
        },
        "entry": {"mode": "issue-backed", "source": "https://github.com/example/project/issues/1"},
        "basis": {
            "kind": "issue",
            "references": ["https://github.com/example/project/issues/1"],
            "verification": {
                "status": "verified",
                "provider": "github",
                "reference": "https://github.com/example/project/issues/1",
                "repository": "example/project",
                "repository_id": 101,
                "verified_at": "2026-08-07T00:00:00Z",
            },
        },
        "contract": {
            "contract_version": "0.1",
            "contribution_id": "contrib-test-001",
            "problem": "A reproducible test failure needs a narrow fix.",
            "non_goals": ["No unrelated refactor"],
            "scope": {"files": ["src/example.py"]},
            "invariants": ["Existing callers keep their behavior."],
            "design": "Guard the invalid input at the existing boundary.",
            "alternatives": [{"option": "Refactor the caller", "rejected_because": "Larger review surface."}],
            "validation_plan": ["Run the focused unit test."],
            "risks": ["A caller may rely on the old exception path."],
            "success_criteria": ["The regression test passes."],
            "max_diff_lines": 20,
            "approval": {"status": "approved", "human_confirmed": True},
        },
        "policy": {
            "authoritative_claims": {"disclosure_required": False},
            "conflicts": [],
            "posture": "explicit",
        },
        "review": {"depth": "standard", "signals": [], "hard_stops": []},
        "ai_assistance": {
            "used": True,
            "stages": [
                {"name": "implementation", "level": "assisted", "human_verified": True},
                {"name": "verification", "level": "reviewed", "human_verified": True},
            ],
            "disclosure": {"text": "AI assistance was reviewed by the contributor.", "locations": ["pr_body"], "human_confirmed": True},
        },
        "diff": {
            "base_sha": "base-sha",
            "head_sha": "head-sha",
            "patch_sha256": "patch-sha256",
            "changed_files": ["src/example.py"],
            "additions": 3,
            "deletions": 1,
        },
        "verification": {
            "commands": ["python -m unittest"],
            "evidence": ["exit 0"],
            "receipts": [{
                "argv": ["python", "-m", "unittest"],
                "cwd": "/workspace/reviewworthy",
                "exit_code": 0,
                "head_sha": "head-sha",
                "stdout_sha256": "stdout-sha256",
                "stderr_sha256": "stderr-sha256",
                "provenance": "cli_executed",
            }],
        },
        "materials": {},
        "results": [
            {"node": node, "status": "passed", "evidence": [f"{node} recorded"]}
            for node in REQUIRED_NODES
        ],
        "understanding": {
            "orientation": {
                "status": "passed",
                "summary": "The contract and evidence were explained.",
                "topics": ["contract", "diff", "verification", "policy"],
                "evidence": ["Orientation covered the material snapshot."],
            },
            "assessment": {
                "status": "passed",
                "questions": ["What boundary protects the invariant?"],
                "answers": ["The existing input boundary validates before the old path runs."],
                "evidence": ["The contributor answered a non-repeating question."],
            },
        },
        "narrative": {
            "title": "Fix invalid input handling",
            "body": "https://github.com/example/project/issues/1\n\n## Why\nFixes the reported regression.\n\n## Testing\n`python -m unittest`",
            "final_preview_confirmed": True,
            "human_expression_required": False,
            "ai_disclosure": "AI assistance was reviewed by the contributor.",
        },
    }
    packet["contract"]["approval"]["contract_sha256"] = contract_snapshot(packet["contract"])
    packet["materials"]["material_snapshot"] = material_snapshot(packet)
    packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
    packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
    return packet
