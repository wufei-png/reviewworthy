from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def test_remote_create_uses_local_receipt_on_immediate_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            body_path = root / "body.md"
            packet = valid_packet()
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
            args = [
                "remote",
                "create",
                "--packet",
                str(packet_path),
                "--repo",
                "example/project",
                "--kind",
                "issue",
                "--title",
                packet["narrative"]["title"],
                "--body-file",
                str(body_path),
                "--confirm-operation-id",
                "",
                "--json",
            ]
            plan_output = io.StringIO()
            with redirect_stdout(plan_output):
                main(args[:1] + ["plan"] + args[2:-3] + ["--json"])
            operation_id = json.loads(plan_output.getvalue())["operation_id"]
            args[args.index("--confirm-operation-id") + 1] = operation_id
            fake_client = unittest.mock.MagicMock()
            fake_client.find_existing.return_value = []
            fake_client.create.return_value = "https://github.com/example/project/issues/7"

            with patch("reviewworthy.cli.GhClient", return_value=fake_client):
                with redirect_stdout(io.StringIO()):
                    first_code = main(args)
                with redirect_stdout(io.StringIO()):
                    second_code = main(args)

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertEqual(fake_client.create.call_count, 1)
