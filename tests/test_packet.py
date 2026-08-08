from __future__ import annotations

import unittest

from reviewworthy.packet import issue_basis_blockers, material_snapshot, readiness_blockers, skeleton_packet, validate_packet

from helpers import valid_packet


class PacketValidationTests(unittest.TestCase):
    def test_packet_01_is_rejected_without_implicit_migration(self) -> None:
        packet = valid_packet()
        packet["packet_version"] = "0.1"

        errors = validate_packet(packet)["errors"]

        self.assertIn("unsupported_packet_version", {error["code"] for error in errors})

    def test_packet_02_requires_complete_merge_base_diff_identity(self) -> None:
        packet = valid_packet()
        packet["diff"].pop("merge_base_sha")

        errors = validate_packet(packet)["errors"]

        self.assertIn("missing_diff_field", {error["code"] for error in errors})

    def test_valid_packet_contains_every_result_and_current_assessment(self) -> None:
        result = validate_packet(valid_packet())
        self.assertTrue(result["valid"], result["errors"])

    def test_absolute_verification_cwd_is_rejected(self) -> None:
        packet = valid_packet()
        packet["verification"]["receipts"][0]["cwd"] = "/workspace/reviewworthy"

        codes = {error["code"] for error in validate_packet(packet)["errors"]}

        self.assertIn("absolute_verification_cwd", codes)

    def test_windows_absolute_verification_cwd_is_rejected_on_posix(self) -> None:
        for cwd in (r"C:\Users\alice\reviewworthy", r"\\server\share\reviewworthy", r"C:verification", r"\verification"):
            packet = valid_packet()
            packet["verification"]["receipts"][0]["cwd"] = cwd

            codes = {error["code"] for error in validate_packet(packet)["errors"]}

            self.assertIn("absolute_verification_cwd", codes, cwd)

    def test_remote_readiness_rejects_receipt_without_clean_worktree_proof(self) -> None:
        packet = valid_packet()
        packet["verification"]["receipts"][0].pop("worktree_clean_before")
        packet["verification"]["receipts"][0].pop("worktree_clean_after")
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertIn("verification_worktree_unverified", codes)

    def test_issue_state_reason_normalization_and_duplicate_label_are_independent(self) -> None:
        for state_reason in ("not_planned", "not-planned", "not planned"):
            packet = valid_packet()
            packet["basis"]["verification"]["state_reason"] = state_reason
            self.assertIn("issue_not_actionable", {blocker["code"] for blocker in issue_basis_blockers(packet)})

        for state_reason in ("completed", "reopened"):
            packet = valid_packet()
            packet["basis"]["verification"]["state_reason"] = state_reason
            self.assertNotIn("issue_not_actionable", {blocker["code"] for blocker in issue_basis_blockers(packet)})

        packet = valid_packet()
        packet["basis"]["verification"]["state_reason"] = "duplicate"
        self.assertNotIn("issue_not_actionable", {blocker["code"] for blocker in issue_basis_blockers(packet)})

        packet = valid_packet()
        packet["basis"]["verification"]["labels"] = ["Duplicate"]
        self.assertIn("issue_duplicate", {blocker["code"] for blocker in issue_basis_blockers(packet)})

        packet["basis"]["verification"]["state_reason"] = "not_planned"
        codes = {blocker["code"] for blocker in issue_basis_blockers(packet)}
        self.assertIn("issue_not_actionable", codes)
        self.assertIn("issue_duplicate", codes)

    def test_unresolved_candidate_duplicate_disposition_blocks_readiness(self) -> None:
        packet = valid_packet()
        packet["candidate_selection"] = {
            "candidate_id": "candidate-potential",
            "repository": "example/project",
            "menu_snapshot": "menu-sha",
            "recommendation": "seek_maintainer_signal",
            "duplicate_disposition": "potential_duplicate",
            "confirmed": True,
        }
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        self.assertIn("duplicate_work_unresolved", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_material_change_invalidates_assessment(self) -> None:
        packet = valid_packet()
        packet["diff"]["additions"] = 99
        result = validate_packet(packet)
        codes = {error["code"] for error in result["errors"]}
        self.assertIn("material_snapshot_mismatch", codes)
        self.assertIn("stale_assessment", codes)

    def test_missing_node_result_is_invalid(self) -> None:
        packet = valid_packet()
        packet["results"] = [result for result in packet["results"] if result["node"] != "narrative"]
        result = validate_packet(packet)
        self.assertIn("missing_result_record", {error["code"] for error in result["errors"]})

    def test_missing_ai_disclosure_record_is_invalid(self) -> None:
        packet = valid_packet()
        packet["ai_assistance"].pop("disclosure")

        result = validate_packet(packet)

        self.assertIn("missing_ai_disclosure_record", {error["code"] for error in result["errors"]})

    def test_ai_used_false_cannot_retain_assistance_stages(self) -> None:
        packet = valid_packet()
        packet["ai_assistance"]["used"] = False

        result = validate_packet(packet)

        self.assertIn("ai_usage_record_conflict", {error["code"] for error in result["errors"]})

    def test_skeleton_records_all_nodes_and_material_snapshot(self) -> None:
        packet = skeleton_packet("draft-001", "discovery")
        self.assertEqual(len(packet["results"]), 7)
        self.assertEqual(packet["entry"]["mode"], "discovery")
        self.assertTrue(packet["materials"]["material_snapshot"])

    def test_discovery_evidence_policy_can_block_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {"kind": "discovery-evidence", "evidence": ["reproduced failure"]}
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = False
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        blockers = readiness_blockers(packet)

        self.assertIn("discovery_evidence_disallowed", {blocker["code"] for blocker in blockers})

    def test_discovery_requires_a_structured_signal_record(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {"kind": "discovery-evidence", "evidence": ["reproduced failure"]}
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        blockers = readiness_blockers(packet)
        codes = {blocker["code"] for blocker in blockers}

        self.assertIn("missing_signal_record", codes)

    def test_pending_signal_allows_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "discovery-evidence",
            "evidence": ["reproduced failure"],
            "signal": {
                "signal_version": "0.1",
                "kind": "reproducible-evidence",
                "reference": "repro://input-regression",
                "status": "pending",
                "evidence": ["exit 1"],
                "published": False,
            },
        }
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertNotIn("signal_not_confirmed", codes)
        self.assertNotIn("signal_unavailable", codes)

    def test_external_signal_requires_recorded_public_verification(self) -> None:
        packet = valid_packet()
        packet["basis"] = {
            "kind": "signal",
            "references": ["https://github.com/example/project/issues/2"],
            "evidence": [],
            "signal": {
                "signal_version": "0.1",
                "kind": "issue",
                "reference": "https://github.com/example/project/issues/2",
                "status": "pending",
                "evidence": [],
                "published": True,
            },
        }
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        blockers = readiness_blockers(packet)

        self.assertIn("signal_verification_required", {blocker["code"] for blocker in blockers})

        packet["basis"]["signal"]["verification"] = {
            "status": "verified",
            "provider": "github",
            "reference": packet["basis"]["signal"]["reference"],
            "verified_at": "2026-08-06T00:00:00Z",
        }
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        self.assertNotIn("signal_verification_required", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_rejected_signal_blocks_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "discovery-evidence",
            "evidence": ["reproduced failure"],
            "signal": {
                "signal_version": "0.1",
                "kind": "reproducible-evidence",
                "reference": "repro://input-regression",
                "status": "rejected",
                "evidence": ["exit 1"],
                "published": False,
            },
        }
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        self.assertIn("signal_unavailable", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_unknown_discovery_policy_blocks_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "discovery-evidence",
            "evidence": ["reproduced failure"],
            "signal": {
                "signal_version": "0.1",
                "kind": "reproducible-evidence",
                "reference": "repro://input-regression",
                "status": "confirmed",
                "evidence": ["exit 1"],
                "published": False,
                "confirmed_at": "2026-08-06T00:00:00Z",
            },
        }
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        self.assertIn("discovery_evidence_policy_unknown", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_confirmed_discovery_signal_clears_signal_specific_blockers(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "discovery-evidence",
            "evidence": ["reproduced failure"],
            "signal": {
                "signal_version": "0.1",
                "kind": "reproducible-evidence",
                "reference": "repro://input-regression",
                "status": "confirmed",
                "evidence": ["exit 1"],
                "published": False,
                "confirmed_at": "2026-08-06T00:00:00Z",
            },
        }
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertNotIn("signal_not_confirmed", codes)
        self.assertNotIn("missing_signal_record", codes)
        self.assertNotIn("discovery_evidence_policy_unknown", codes)

    def test_remote_readiness_checks_scope_and_diff_budget(self) -> None:
        packet = valid_packet()
        packet["diff"] = {"changed_files": ["src/example.py", "src/unapproved.py"], "additions": 99, "deletions": 0}
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertIn("out_of_scope_files", codes)
        self.assertIn("diff_budget_exceeded", codes)

    def test_missing_diff_budget_blocks_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["contract"].pop("max_diff_lines")
        packet["diff"].pop("additions")
        packet["diff"].pop("deletions")
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertIn("missing_diff_budget", codes)

    def test_contract_approval_is_required_for_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["contract"]["approval"] = {"status": "not_run", "human_confirmed": False}

        self.assertIn("contract_not_approved", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_orientation_must_pass_before_assessment(self) -> None:
        packet = valid_packet()
        packet["understanding"]["orientation"]["status"] = "not_run"

        self.assertIn("orientation_not_passed", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_verification_evidence_is_required_for_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["verification"] = {"commands": [], "evidence": []}
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        self.assertIn("missing_verification_evidence", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_risk_signal_cannot_use_standard_depth(self) -> None:
        packet = valid_packet()
        packet["review"]["signals"] = ["public_api"]

        self.assertIn("review_depth_too_low", {error["code"] for error in validate_packet(packet)["errors"]})

    def test_heightened_review_requires_human_expression(self) -> None:
        packet = valid_packet()
        packet["review"]["depth"] = "heightened"
        packet["narrative"]["human_expression"] = ""
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        self.assertIn("missing_human_expression", {error["code"] for error in validate_packet(packet)["errors"]})

    def test_packet_and_contract_ids_must_match(self) -> None:
        packet = valid_packet()
        packet["contract"]["contribution_id"] = "other-contribution"
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        self.assertIn("contribution_id_mismatch", {error["code"] for error in validate_packet(packet)["errors"]})

    def test_missing_policy_posture_uses_conservative_remote_fallback(self) -> None:
        packet = valid_packet()
        packet["policy"].pop("posture")
        packet["ai_assistance"]["disclosure"] = {"text": "", "locations": [], "human_confirmed": False}
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        blockers = readiness_blockers(packet)

        self.assertIn("missing_ai_disclosure", {blocker["code"] for blocker in blockers})
