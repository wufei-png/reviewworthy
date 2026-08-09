from __future__ import annotations

from reviewworthy.contract import contract_snapshot
from reviewworthy.git import verification_plan_digest
from reviewworthy.packet import REQUIRED_NODES, semantic_snapshot


def valid_packet() -> dict:
    packet = {
        "packet_version": "0.3",
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
                "record_type": "issue",
                "host": "github.com",
                "number": 1,
                "url": "https://github.com/example/project/issues/1",
                "visibility": "public",
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
        "review": {"profile": "standard", "signals": [], "hard_stops": []},
        "ai_assistance": {
            "used": True,
            "stages": [
                {"name": "implementation", "level": "assisted", "human_verified": True},
                {"name": "verification", "level": "reviewed", "human_verified": True},
            ],
            "disclosure": {"text": "AI assistance was reviewed by the contributor.", "locations": ["pr_body"], "human_confirmed": True},
        },
        "diff": {
            "comparison": "merge_base",
            "base_tip_sha": "base-sha",
            "merge_base_sha": "merge-base-sha",
            "head_sha": "head-sha",
            "subject_digest": "subject-digest",
            "fingerprint_algorithm": "git-raw-content-v1",
            "changed_files": ["src/example.py"],
            "additions": 3,
            "deletions": 1,
        },
        "verification": {
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
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:01Z",
                "head_sha": "head-sha",
                "head_sha_before": "head-sha",
                "head_sha_after": "head-sha",
                "worktree_clean_before": True,
                "worktree_clean_after": True,
                "stdout_sha256": "stdout-sha256",
                "stderr_sha256": "stderr-sha256",
                "provenance": "contributor_local",
            }],
        },
        "ownership": {
            "status": "passed",
            "problem": "The contributor can explain the reported failure.",
            "scope": "Only src/example.py changes.",
            "verification": "The unit check covers the changed boundary.",
            "risks": ["Existing callers may depend on the old exception path."],
        },
        "snapshots": {},
        "results": [
            {"node": node, "status": "passed", "evidence": [f"{node} recorded"]}
            for node in REQUIRED_NODES
        ],
        "understanding": {
            "orientation": {
                "status": "passed",
                "summary": "The contract and evidence were explained.",
                "topics": ["contract", "diff", "verification", "policy"],
                "rubric": {
                    "covered": ["behavior", "invariant", "test"],
                    "evidence": {
                        "behavior": "The boundary rejects the invalid input.",
                        "invariant": "Existing callers retain their behavior.",
                        "test": "The focused regression test exercises the boundary.",
                    },
                },
                "evidence": ["Orientation covered the material snapshot."],
            },
            "assessment": {
                "status": "passed",
                "questions": ["What boundary protects the invariant?"],
                "answers": ["The existing input boundary validates before the old path runs."],
                "rubric": {
                    "covered": ["behavior", "invariant", "test"],
                    "evidence": {
                        "behavior": "The invalid input follows the guarded path.",
                        "invariant": "The existing caller contract remains unchanged.",
                        "test": "The regression command covers the changed path.",
                    },
                },
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
    packet["verification"]["plan_digest"] = verification_plan_digest(packet["verification"]["plan"])
    packet["verification"]["receipts"][0]["plan_digest"] = packet["verification"]["plan_digest"]
    packet["snapshots"]["semantic"] = semantic_snapshot(packet)
    packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
    packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
    return packet
