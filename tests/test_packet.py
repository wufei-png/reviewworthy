from __future__ import annotations

import unittest

from reviewworthy.packet import material_snapshot, readiness_blockers, skeleton_packet, validate_packet

from helpers import valid_packet


class PacketValidationTests(unittest.TestCase):
    def test_valid_packet_contains_every_result_and_current_assessment(self) -> None:
        result = validate_packet(valid_packet())
        self.assertTrue(result["valid"], result["errors"])

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

    def test_pending_signal_blocks_remote_readiness(self) -> None:
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
            },
        }
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        self.assertIn("signal_not_confirmed", {blocker["code"] for blocker in readiness_blockers(packet)})

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
