from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from reviewworthy.cli import main

from helpers import valid_packet


class CliBoundaryTests(unittest.TestCase):
    def test_remote_plan_uses_the_approved_packet_narrative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            body_path = root / "body.md"
            packet = valid_packet()
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                code = main(
                    [
                        "remote",
                        "plan",
                        "--packet",
                        str(packet_path),
                        "--repo",
                        "example/project",
                        "--kind",
                        "pull_request",
                        "--title",
                        packet["narrative"]["title"],
                        "--body-file",
                        str(body_path),
                        "--head",
                        "fix/input",
                        "--json",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertIn('"operation_id"', output.getvalue())

            with redirect_stdout(io.StringIO()):
                mismatch_code = main(
                    [
                        "remote",
                        "plan",
                        "--packet",
                        str(packet_path),
                        "--repo",
                        "example/project",
                        "--kind",
                        "pull_request",
                        "--title",
                        "Unapproved title",
                        "--body-file",
                        str(body_path),
                        "--head",
                        "fix/input",
                        "--json",
                    ]
                )
            self.assertEqual(mismatch_code, 2)
