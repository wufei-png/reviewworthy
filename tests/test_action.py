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
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            result = check_packet(path)
            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(result["unknowns"])
