from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reviewworthy.brief import build_project_brief, render_project_brief, validate_project_brief
from reviewworthy.candidate import render_candidate_menu, skeleton_menu, validate_candidate_menu
from reviewworthy.contract import skeleton_contract, validate_contract
from reviewworthy.disclosure import disclosure_errors, render_disclosure


class ArtifactTests(unittest.TestCase):
    def test_project_brief_is_deterministic_and_keeps_prose_skill_owned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("A small project.\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='example'\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_example.py").write_text("def test_example(): pass\n", encoding="utf-8")

            first = build_project_brief(root)
            second = build_project_brief(root)

            self.assertEqual(first, second)
            self.assertTrue(validate_project_brief(first)["valid"])
            self.assertEqual(first["status"], "source-manifest-only")
            self.assertEqual(first["human_sections"]["problem"], "")
            self.assertFalse(any("__pycache__" in source["path"] for source in first["sources"]))
            self.assertIn("# Project brief", render_project_brief(first))

    def test_candidate_menu_rejects_single_numeric_score_and_duplicate_direct_plan(self) -> None:
        menu = skeleton_menu("example/project")
        candidate = {
            "id": "candidate-001",
            "title": "Existing work",
            "basis": {"kind": "issue", "references": ["https://example/1"]},
            "duplicate_search": {"checked": True, "matches": [{"number": 1}]},
            "value": {"summary": "Already covered"},
            "scope": {"files": ["src/example.py"]},
            "review_cost": "small",
            "verifiability": "high",
            "risk": [],
            "recommendation": "plan_directly",
            "score": 0.99,
        }
        menu["candidates"] = [candidate]
        result = validate_candidate_menu(menu)
        codes = {error["code"] for error in result["errors"]}
        self.assertIn("numeric_score_not_allowed", codes)
        self.assertIn("duplicate_work_recommendation_mismatch", codes)

    def test_contract_skeleton_is_explicitly_incomplete(self) -> None:
        result = validate_contract(skeleton_contract("contract-001"))
        self.assertFalse(result["valid"])
        self.assertIn("empty_contract_text", {error["code"] for error in result["errors"]})

    def test_disclosure_locations_and_stages_are_policy_bound(self) -> None:
        packet = {
            "policy": {
                "posture": "explicit",
                "authoritative_claims": {
                    "disclosure_required": True,
                    "disclosure_locations": ["commit_trailer"],
                    "disclosure_stages": ["verification"],
                },
            },
            "narrative": {
                "ai_disclosure": {
                    "text": "Assistance was reviewed.",
                    "locations": ["pr_body"],
                    "human_confirmed": True,
                }
            },
            "ai_assistance": {"stages": [{"name": "implementation"}]},
        }
        codes = {error["code"] for error in disclosure_errors(packet)}
        self.assertIn("missing_disclosure_location", codes)
        self.assertIn("missing_disclosure_stage", codes)
        rendered = render_disclosure(packet, "commit_trailer")
        self.assertEqual(rendered["location"], "commit_trailer")
        self.assertIn("Assistance was reviewed", rendered["text"])
