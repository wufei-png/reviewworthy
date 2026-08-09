from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from reviewworthy.cli import main
from reviewworthy.packet import semantic_snapshot
from reviewworthy.workflow import workflow_status

from helpers import valid_packet


class WorkflowStatusTests(unittest.TestCase):
    def test_ready_packet_has_remote_plan_as_next_step(self) -> None:
        result = workflow_status(valid_packet(), Path("packet.json"))

        self.assertTrue(result["ready"])
        self.assertEqual(result["current_stage"], "ready")
        self.assertIn("remote plan", result["next"][0]["command"])

    def test_missing_current_receipt_points_to_exact_required_check(self) -> None:
        packet = valid_packet()
        packet["verification"]["receipts"] = []
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        result = workflow_status(packet, Path("packet.json"))

        self.assertFalse(result["ready"])
        self.assertEqual(result["current_stage"], "verification")
        self.assertIn("--check-id unit", result["next"][0]["command"])

    def test_stale_head_receipt_points_to_exact_required_check(self) -> None:
        packet = valid_packet()
        packet["verification"]["receipts"][0]["head_sha"] = "f" * 40
        packet["verification"]["receipts"][0]["head_sha_before"] = "f" * 40
        packet["verification"]["receipts"][0]["head_sha_after"] = "f" * 40
        snapshot = semantic_snapshot(packet)
        packet["snapshots"]["semantic"] = snapshot
        packet["understanding"]["orientation"]["semantic_snapshot"] = snapshot
        packet["understanding"]["assessment"]["semantic_snapshot"] = snapshot

        result = workflow_status(packet, Path("packet.json"))

        self.assertEqual(result["current_stage"], "verification")
        self.assertIn("verification_head_mismatch", {item["code"] for item in result["blocking"]})
        self.assertIn("--check-id unit", result["next"][0]["command"])

    def test_next_cli_returns_one_machine_readable_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            packet = valid_packet()
            packet["verification"]["receipts"] = []
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
            path.write_text(json.dumps(packet), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                code = main(["next", "--packet", str(path), "--json"])

            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(len(result["next"]), 1)
            self.assertEqual(result["status_version"], "0.3")

    def test_discussion_signal_does_not_suggest_issue_verification(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "signal",
            "references": [],
            "summary": "A public design discussion",
            "signal": {
                "signal_version": "0.3",
                "record_type": "discussion",
                "claim_type": "accepted_proposal",
                "lifecycle": "pending",
                "reference": "https://github.com/org/repo/discussions/7",
                "evidence": [],
                "authority": {"kind": "contributor", "actor": "", "asserted_at": ""},
            },
        }
        snapshot = semantic_snapshot(packet)
        packet["snapshots"]["semantic"] = snapshot
        packet["understanding"]["orientation"]["semantic_snapshot"] = snapshot
        packet["understanding"]["assessment"]["semantic_snapshot"] = snapshot

        result = workflow_status(packet, Path("packet.json"))

        self.assertEqual(result["current_stage"], "basis")
        self.assertEqual(result["next"][0]["kind"], "decision")
        self.assertNotIn("issue verify", result["next"][0]["reason"])
