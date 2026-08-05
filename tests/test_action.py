from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from reviewworthy.action import check_packet
from reviewworthy.packet import material_snapshot

from helpers import valid_packet


class ActionCheckTests(unittest.TestCase):
    def test_missing_packet_is_unknown_but_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = check_packet(Path(directory) / "missing.json")
            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(result["unknowns"])

    def test_action_fails_deterministic_scope_violation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(valid_packet()), encoding="utf-8")
            result = check_packet(path, ["src/example.py", "src/unapproved.py"])
            self.assertEqual(result["conclusion"], "failure")
            self.assertEqual(result["violations"][0]["code"], "out_of_scope_files")

    def test_action_reports_unknown_policy_without_blocking_valid_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"] = {}
            packet["ai_assistance"]["disclosure"] = {"text": "", "locations": [], "human_confirmed": False}
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            result = check_packet(path)
            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(result["unknowns"])

    def test_action_fails_explicit_disclosure_violation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"]["authoritative_claims"] = {
                "ai_assistance": "allowed",
                "issue_required": False,
                "disclosure_required": True,
                "disclosure_locations": ["pr_body"],
                "disclosure_stages": [],
                "human_pr_narrative_required": False,
                "security_private_reporting": False,
                "draft_pr_required": False,
                "discovery_evidence_allowed": True,
                "good_first_issue_ai_allowed": True,
            }
            packet["ai_assistance"]["disclosure"] = {"text": "", "locations": [], "human_confirmed": False}
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "failure")
            self.assertIn("missing_ai_disclosure", {violation["code"] for violation in result["violations"]})

    def test_action_fails_ai_prohibited_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"]["authoritative_claims"]["ai_assistance"] = "prohibited"
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "failure")
            self.assertIn("ai_assistance_prohibited", {violation["code"] for violation in result["violations"]})

    def test_action_reports_module_scope_as_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["contract"]["scope"] = {"modules": ["input boundary"]}
            packet["diff"]["changed_files"] = ["src/unapproved.py"]
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(any("module-based" in unknown.lower() for unknown in result["unknowns"]))

    def test_action_keeps_mixed_scope_file_allowlist_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["contract"]["scope"] = {"files": ["src/example.py"], "modules": ["input boundary"]}
            packet["diff"]["changed_files"] = ["src/unapproved.py"]
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "failure")
            self.assertIn("out_of_scope_files", {violation["code"] for violation in result["violations"]})

    def test_action_reports_incomplete_explicit_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"] = {"posture": "explicit", "authoritative_claims": {"ai_assistance": "allowed", "disclosure_required": False}}
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(any("incomplete" in unknown.lower() for unknown in result["unknowns"]))

    def test_action_handles_invalid_changed_file_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["diff"]["changed_files"] = [{"path": "src/unapproved.py"}]
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "failure")
            self.assertIn("invalid_changed_file", {violation["code"] for violation in result["violations"]})
