from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reviewworthy.cli import main
from reviewworthy.packet import readiness_blockers, semantic_snapshot, skeleton_packet
from reviewworthy.packet_mutation import maintain_packet, record_basis
from reviewworthy.signal import skeleton_signal

from helpers import valid_packet


def node(packet: dict, name: str) -> dict:
    return next(record for record in packet["results"] if record["node"] == name)


class PacketMutationTests(unittest.TestCase):
    def call(self, *args: str) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([*args, "--json"])
        return code, json.loads(output.getvalue())

    def test_policy_and_issue_record_progress_incomplete_packet_without_provider_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "packet.json"
            path.write_text(json.dumps(skeleton_packet("fresh", "issue-backed")))
            (root / "README.md").write_text("AI assistance is allowed.\n")
            with patch("reviewworthy.cli.GhClient") as provider:
                self.assertEqual(self.call("packet", "policy", "bind", "--root", str(root), "--packet", str(path))[0], 0)
                self.assertEqual(self.call("packet", "basis", "record", "--packet", str(path), "--issue", "https://github.com/example/project/issues/1")[0], 0)
                provider.assert_not_called()
            packet = json.loads(path.read_text())
            self.assertEqual(packet["repository"]["owner"], "example")
            self.assertNotIn("candidate_selection", packet)
            self.assertEqual(node(packet, "policy_check")["status"], "passed")
            self.assertEqual(node(packet, "contribution_basis")["status"], "blocked")
            self.assertIn("issue_verification_required", {error["code"] for error in readiness_blockers(packet)})

    def test_changed_basis_resets_approval_and_downstream_evidence_preserves_candidate_gates(self) -> None:
        packet = valid_packet()
        packet["candidate_selection"] = {"recommendation": "issue_only", "duplicate_disposition": "potential_duplicate"}
        updated = maintain_packet(packet, record_basis(packet, issue="https://github.com/example/project/issues/2"))
        self.assertEqual(updated["contract"]["approval"]["status"], "not_run")
        self.assertNotIn("verification", updated["basis"])
        self.assertEqual(updated["verification"]["receipts"], [])
        self.assertEqual(updated["understanding"]["orientation"]["status"], "not_run")
        self.assertEqual(updated["understanding"]["orientation"]["semantic_snapshot"], packet["understanding"]["orientation"]["semantic_snapshot"])
        self.assertFalse(updated["narrative"]["final_preview_confirmed"])
        self.assertEqual(node(updated, "implementation")["status"], "not_run")
        self.assertEqual(updated["candidate_selection"], packet["candidate_selection"])
        self.assertEqual(updated["snapshots"]["semantic"], semantic_snapshot(updated))

    def test_identical_issue_and_audit_refresh_preserve_current_evidence(self) -> None:
        packet = valid_packet()
        updated = maintain_packet(packet, record_basis(packet, issue=packet["basis"]["references"][0]))
        self.assertEqual(updated["contract"]["approval"], packet["contract"]["approval"])
        self.assertEqual(updated["verification"]["receipts"], packet["verification"]["receipts"])
        changed = deepcopy(packet)
        changed["basis"]["verification"]["verified_at"] = "later"
        updated = maintain_packet(packet, changed)
        self.assertEqual(updated["contract"]["approval"], packet["contract"]["approval"])
        self.assertEqual(updated["understanding"], packet["understanding"])

    def test_foreign_basis_and_invalid_signal_leave_packet_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(valid_packet()))
            before = path.read_bytes()
            code, _ = self.call("packet", "basis", "record", "--packet", str(path), "--issue", "https://github.com/other/project/issues/1")
            self.assertEqual(code, 2)
            self.assertEqual(path.read_bytes(), before)
        signal = skeleton_signal("issue", "bug_report", "https://github.com/example/project/issues/2")
        signal["verification"] = {"status": "verified", "provider": "github"}
        with self.assertRaises(ValueError):
            record_basis(valid_packet(), signal=signal)

    def test_unverified_external_signal_records_basis_but_cannot_pass_it(self) -> None:
        signal = skeleton_signal("discussion", "accepted_proposal", "https://github.com/example/project/discussions/3")
        packet = valid_packet()
        updated = maintain_packet(packet, record_basis(packet, signal=signal))
        self.assertEqual(node(updated, "contribution_basis")["status"], "blocked")
        self.assertIn("signal_verification_required", {error["code"] for error in readiness_blockers(updated)})

    def test_issue_verification_record_maintains_basis_result(self) -> None:
        packet = skeleton_packet("fresh", "issue-backed", "example/project")
        packet = maintain_packet(packet, record_basis(packet, issue="https://github.com/example/project/issues/1"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet))
            remote = {**valid_packet()["basis"]["verification"], "verified": True, "labels": []}
            with patch("reviewworthy.cli.GhClient") as provider:
                provider.return_value.verify_public_reference.return_value = remote
                self.assertEqual(self.call("issue", "verify", "--packet", str(path), "--record")[0], 0)
            updated = json.loads(path.read_text())
        self.assertEqual(node(updated, "contribution_basis")["status"], "passed")
        self.assertEqual(updated["repository"]["repository_id"], 101)
