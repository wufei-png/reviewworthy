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

    def test_missing_policy_posture_uses_conservative_remote_fallback(self) -> None:
        packet = valid_packet()
        packet["policy"].pop("posture")
        packet["ai_assistance"]["disclosure"] = {"text": "", "locations": [], "human_confirmed": False}
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)

        blockers = readiness_blockers(packet)

        self.assertIn("missing_ai_disclosure", {blocker["code"] for blocker in blockers})
