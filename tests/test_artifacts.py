from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reviewworthy.brief import build_project_brief, render_project_brief, validate_project_brief
from reviewworthy.candidate import bind_candidate, render_candidate_menu, select_candidate, skeleton_menu, transition_candidate, validate_candidate_menu
from reviewworthy.contract import skeleton_contract, validate_contract
from reviewworthy.disclosure import disclosure_errors, render_disclosure
from reviewworthy.packet import semantic_snapshot
from reviewworthy.packet import readiness_blockers
from reviewworthy.signal import skeleton_signal
from reviewworthy.understanding import record_understanding, validate_understanding

from helpers import valid_packet
from reviewworthy.util import sha256_json


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
            "duplicate_search": {"checked": True, "matches": [{"number": 1}], "disposition": "exact_duplicate"},
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

    def test_candidate_render_includes_module_only_scope(self) -> None:
        menu = skeleton_menu("example/project")
        menu["candidates"] = [{
            "id": "candidate-002",
            "title": "Module work",
            "basis": {"kind": "signal", "references": ["https://example/2"]},
            "duplicate_search": {"checked": True, "matches": [], "disposition": "not_duplicate"},
            "value": {"summary": "A bounded module improvement"},
            "scope": {"modules": ["input boundary"]},
            "review_cost": "small",
            "verifiability": "high",
            "risk": [],
            "recommendation": "plan_directly",
        }]

        rendered = render_candidate_menu(menu)

        self.assertIn("module:input boundary", rendered)

    def test_confirmed_candidate_selection_binds_basis_and_provenance(self) -> None:
        menu = skeleton_menu("example/project")
        menu["candidates"] = [{
            "id": "candidate-003",
            "title": "Narrow fix",
            "basis": {"kind": "issue", "references": ["https://github.com/example/project/issues/3"], "evidence": []},
            "duplicate_search": {"checked": True, "matches": [], "disposition": "not_duplicate"},
            "value": {"summary": "Fixes a reported regression"},
            "scope": {"files": ["src/example.py"]},
            "review_cost": "small",
            "verifiability": "high",
            "risk": [],
            "recommendation": "plan_directly",
        }]
        selected = select_candidate(menu, "candidate-003", confirmed=True)
        bound = bind_candidate(selected, valid_packet(), "candidate-003")

        self.assertEqual(bound["basis"]["references"], ["https://github.com/example/project/issues/3"])
        self.assertEqual(bound["entry"]["mode"], "issue-backed")
        self.assertEqual(bound["candidate_selection"]["candidate_id"], "candidate-003")
        self.assertNotEqual(bound["snapshots"]["semantic"], semantic_snapshot(bound))

    def test_confirming_signal_candidate_requires_a_structured_signal(self) -> None:
        menu = skeleton_menu("example/project")
        menu["candidates"] = [{
            "id": "candidate-004",
            "title": "Signal-backed work",
            "basis": {"kind": "signal", "references": ["https://github.com/example/project/issues/4"], "evidence": []},
            "duplicate_search": {"checked": True, "matches": [], "disposition": "not_duplicate"},
            "value": {"summary": "A requested change"},
            "scope": {"files": ["src/example.py"]},
            "review_cost": "small",
            "verifiability": "high",
            "risk": [],
            "recommendation": "plan_directly",
        }]

        with self.assertRaises(ValueError):
            select_candidate(menu, "candidate-004", confirmed=True)

    def test_unavailable_signal_cannot_be_bound(self) -> None:
        menu = skeleton_menu("example/project")
        menu["candidates"] = [{
            "id": "candidate-005",
            "title": "Unavailable work",
            "basis": {
                "kind": "signal",
                "references": ["https://github.com/example/project/issues/5"],
                "evidence": [],
                "signal": {
                    **skeleton_signal("issue", "bug_report", "https://github.com/example/project/issues/5"),
                    "lifecycle": "rejected",
                },
            },
            "duplicate_search": {"checked": True, "matches": [], "disposition": "not_duplicate"},
            "value": {"summary": "No longer wanted"},
            "scope": {"files": ["src/example.py"]},
            "review_cost": "small",
            "verifiability": "high",
            "risk": [],
            "recommendation": "plan_directly",
        }]
        menu["selection"] = {"selected_id": "candidate-005", "confirmed": True}

        with self.assertRaises(ValueError):
            bind_candidate(menu, valid_packet(), "candidate-005")

    def test_contract_skeleton_is_explicitly_incomplete(self) -> None:
        result = validate_contract(skeleton_contract("contract-001"))
        self.assertFalse(result["valid"])
        self.assertIn("empty_contract_text", {error["code"] for error in result["errors"]})

    def test_contract_bool_diff_budget_is_invalid(self) -> None:
        contract = skeleton_contract("contract-002")
        contract.update({
            "problem": "A bounded problem",
            "design": "A bounded design",
            "non_goals": [],
            "invariants": [],
            "alternatives": [],
            "validation_plan": [],
            "risks": [],
            "success_criteria": [],
            "scope": {"files": ["src/example.py"]},
            "max_diff_lines": True,
        })

        result = validate_contract(contract)

        self.assertIn("invalid_diff_budget", {error["code"] for error in result["errors"]})

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
            "ai_assistance": {
                "used": True,
                "stages": [{"name": "implementation"}],
                "disclosure": {
                    "text": "Assistance was reviewed.",
                    "locations": ["pr_body"],
                    "human_confirmed": True,
                },
            },
        }
        codes = {error["code"] for error in disclosure_errors(packet)}
        self.assertIn("missing_disclosure_location", codes)
        self.assertIn("missing_disclosure_stage", codes)
        with self.assertRaises(ValueError):
            render_disclosure(packet, "pr_body")
        rendered = render_disclosure(packet, "commit_trailer")
        self.assertEqual(rendered["location"], "commit_trailer")
        self.assertIn("Assistance was reviewed", rendered["text"])

        packet["ai_assistance"]["used"] = False
        self.assertEqual(disclosure_errors(packet), [])
        self.assertEqual(render_disclosure(packet)["text"], "")

    def test_legacy_narrative_disclosure_is_not_read(self) -> None:
        packet = {
            "policy": {"posture": "explicit", "authoritative_claims": {"disclosure_required": True}},
            "narrative": {"ai_disclosure": "Legacy disclosure"},
            "ai_assistance": {"used": True, "stages": []},
        }

        with self.assertRaises(ValueError):
            render_disclosure(packet)

    def test_disclosure_rejects_policy_disallowed_record_location(self) -> None:
        packet = {
            "policy": {"posture": "explicit", "authoritative_claims": {"disclosure_required": True, "disclosure_locations": ["commit_trailer"]}},
            "ai_assistance": {
                "used": True,
                "stages": [],
                "disclosure": {"text": "Reviewed.", "locations": ["commit_trailer", "pr_body"], "human_confirmed": True},
            },
        }

        self.assertIn("disallowed_disclosure_location", {error["code"] for error in disclosure_errors(packet)})

    def test_optional_disclosure_without_allowed_location_renders_empty(self) -> None:
        packet = {
            "policy": {"posture": "explicit", "authoritative_claims": {"disclosure_required": False}},
            "ai_assistance": {"used": True, "stages": [], "disclosure": {"text": "", "locations": [], "human_confirmed": False}},
        }

        rendered = render_disclosure(packet)

        self.assertFalse(rendered["required"])
        self.assertIsNone(rendered["location"])
        self.assertEqual(rendered["text"], "")

    def test_brief_validator_rejects_renderer_missing_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            brief = build_project_brief(Path(directory))
            brief.pop("tooling")
            brief.pop("policy")
            brief["source_manifest_sha256"] = sha256_json({"sources": brief["sources"], "tooling": {}, "policy": {}})

            result = validate_project_brief(brief)

            codes = {error["code"] for error in result["errors"]}
            self.assertIn("missing_tooling", codes)
            self.assertIn("missing_policy", codes)

    def test_brief_freshness_check_detects_repository_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Initial project.\n", encoding="utf-8")
            brief = build_project_brief(root)
            (root / "README.md").write_text("Changed project.\n", encoding="utf-8")

            result = validate_project_brief(brief, root)

            self.assertIn("stale_source_manifest", {error["code"] for error in result["errors"]})

    def test_brief_records_explicit_focus_file_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            focus = root / "src"
            focus.mkdir()
            target = focus / "input.py"
            target.write_text("return 1\n", encoding="utf-8")

            brief = build_project_brief(root, ["src/input.py"])

            self.assertEqual(brief["focus_files"][0]["path"], "src/input.py")
            self.assertEqual(brief["focus_files"][0]["kind"], "focus")
            self.assertTrue(validate_project_brief(brief, root)["valid"])
            target.write_text("return 2\n", encoding="utf-8")
            self.assertIn("stale_source_manifest", {error["code"] for error in validate_project_brief(brief, root)["errors"]})

    def test_brief_validate_reports_deleted_focus_file_as_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "README.md"
            target.write_text("focus\n", encoding="utf-8")
            brief = build_project_brief(root, ["README.md"])
            target.unlink()

            result = validate_project_brief(brief, root)

            self.assertFalse(result["valid"])
            self.assertIn("invalid_focus_file", {error["code"] for error in result["errors"]})

    def test_understanding_requires_orientation_topics_and_material_binding(self) -> None:
        understanding = {
            "orientation": {
                "status": "passed",
                "summary": "Explained the change.",
                "topics": ["contract"],
                "evidence": [],
                "rubric": {"covered": ["behavior", "invariant", "test"], "evidence": {"behavior": "b", "invariant": "i", "test": "t"}},
                "semantic_snapshot": "snapshot-1",
            },
            "assessment": {
                "status": "passed",
                "questions": ["What changed?"],
                "answers": ["The boundary changed."],
                "evidence": [],
                "rubric": {"covered": ["behavior", "invariant", "test"], "evidence": {"behavior": "b", "invariant": "i", "test": "t"}},
                "semantic_snapshot": "snapshot-1",
            },
        }

        result = validate_understanding(understanding, "snapshot-2")

        codes = {error["code"] for error in result["errors"]}
        self.assertIn("missing_orientation_topics", codes)
        self.assertIn("stale_orientation", codes)
        self.assertIn("stale_assessment", codes)

    def test_understanding_heightened_depth_requires_failure_and_tradeoff_categories(self) -> None:
        understanding = {
            "orientation": {
                "status": "passed", "summary": "Explained.", "topics": ["contract", "diff", "verification", "policy"], "evidence": [],
                "rubric": {"covered": ["behavior", "invariant", "test"], "evidence": {"behavior": "b", "invariant": "i", "test": "t"}},
                "semantic_snapshot": "snapshot-1",
            },
            "assessment": {
                "status": "passed", "questions": ["What fails?"], "answers": ["The invalid input is rejected."], "evidence": [],
                "rubric": {"covered": ["behavior", "invariant", "test"], "evidence": {"behavior": "b", "invariant": "i", "test": "t"}},
                "semantic_snapshot": "snapshot-1",
            },
        }

        result = validate_understanding(understanding, "snapshot-1", review_profile="heightened")

        self.assertIn("missing_rubric_categories", {error["code"] for error in result["errors"]})

    def test_candidate_dispositions_allow_investigation_but_block_exact_implementation(self) -> None:
        menu = skeleton_menu("example/project")
        menu["candidates"] = [{
            "id": "candidate-potential",
            "title": "Potentially overlapping fix",
            "basis": {"kind": "issue", "references": ["https://github.com/example/project/issues/9"], "evidence": []},
            "duplicate_search": {"checked": True, "matches": [{"number": 2}], "disposition": "potential_duplicate"},
            "value": {"summary": "Needs investigation"},
            "scope": {"files": ["src/example.py"]},
            "review_cost": "medium",
            "verifiability": "high",
            "risk": [],
            "recommendation": "seek_maintainer_signal",
        }]
        selected = select_candidate(menu, "candidate-potential", confirmed=True)

        bound = bind_candidate(selected, valid_packet(), "candidate-potential")

        self.assertEqual(bound["candidate_selection"]["duplicate_disposition"], "potential_duplicate")
        with self.assertRaises(ValueError):
            select_candidate({**menu, "candidates": [{**menu["candidates"][0], "recommendation": "plan_directly"}]}, "candidate-potential", confirmed=True)

    def test_advisory_candidate_recommendation_needs_confirmed_transition_before_readiness(self) -> None:
        menu = skeleton_menu("example/project")
        menu["candidates"] = [{
            "id": "candidate-transition",
            "title": "Issue-first work",
            "basis": {"kind": "issue", "references": ["https://github.com/example/project/issues/10"], "evidence": []},
            "duplicate_search": {"checked": True, "matches": [], "disposition": "not_duplicate"},
            "value": {"summary": "Needs a public issue first"},
            "scope": {"files": ["src/example.py"]},
            "review_cost": "small",
            "verifiability": "high",
            "risk": [],
            "recommendation": "issue_only",
        }]
        selected = select_candidate(menu, "candidate-transition", confirmed=True)
        bound = bind_candidate(selected, valid_packet(), "candidate-transition")

        self.assertIn("candidate_transition_required", {blocker["code"] for blocker in readiness_blockers(bound)})

        transitioned = transition_candidate(
            bound,
            to="plan_directly",
            reason="A valid public Issue now exists.",
            human_confirmed=True,
        )
        self.assertEqual(transitioned["candidate_selection"]["transition"]["from"], "issue_only")
        self.assertNotIn("candidate_transition_required", {blocker["code"] for blocker in readiness_blockers(transitioned)})

    def test_candidate_transition_requires_reason_and_confirmation(self) -> None:
        packet = valid_packet()
        packet["candidate_selection"] = {
            "candidate_id": "candidate-transition",
            "repository": "example/project",
            "menu_snapshot": "menu-sha",
            "recommendation": "seek_maintainer_signal",
            "duplicate_disposition": "not_duplicate",
            "confirmed": True,
        }

        with self.assertRaises(ValueError):
            transition_candidate(packet, to="plan_directly", reason="", human_confirmed=True)
        with self.assertRaises(ValueError):
            transition_candidate(packet, to="plan_directly", reason="A signal is public.", human_confirmed=False)

    def test_candidate_transition_rejects_incomplete_current_selection(self) -> None:
        packet = valid_packet()
        packet["candidate_selection"] = {
            "candidate_id": "candidate-old",
            "repository": "example/project",
            "menu_snapshot": "menu-sha",
            "duplicate_disposition": "not_duplicate",
            "confirmed": True,
        }

        with self.assertRaises(ValueError):
            transition_candidate(
                packet,
                to="plan_directly",
                reason="The advisory path is now explicitly confirmed.",
                human_confirmed=True,
            )

    def test_passed_assessment_requires_passed_orientation(self) -> None:
        understanding = {
            "orientation": {
                "status": "not_run",
                "summary": "",
                "topics": [],
                "evidence": [],
                "semantic_snapshot": "snapshot-1",
            },
            "assessment": {
                "status": "passed",
                "questions": ["What changed?"],
                "answers": ["The boundary changed."],
                "evidence": [],
                "semantic_snapshot": "snapshot-1",
            },
        }

        result = validate_understanding(understanding, "snapshot-1")

        self.assertIn("assessment_requires_orientation", {error["code"] for error in result["errors"]})

    def test_record_understanding_binds_both_phases_to_given_snapshot(self) -> None:
        packet = {"understanding": {}}
        packet = record_understanding(packet, "orientation", "passed", "snapshot-3", summary="Explained.", topics=["contract", "diff", "verification", "policy"])
        packet = record_understanding(packet, "assessment", "passed", "snapshot-3", questions=["What changed?"], answers=["The boundary changed."])

        self.assertEqual(packet["understanding"]["orientation"]["semantic_snapshot"], "snapshot-3")
        self.assertEqual(packet["understanding"]["assessment"]["answers"], ["The boundary changed."])
