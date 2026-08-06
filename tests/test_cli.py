from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reviewworthy.cli import main
from reviewworthy.github import GhError

from helpers import valid_packet


class CliBoundaryTests(unittest.TestCase):
    def test_signal_init_and_require_confirmed_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            signal_path = Path(directory) / "signal.json"
            with redirect_stdout(io.StringIO()):
                init_code = main(
                    [
                        "signal",
                        "init",
                        "--kind",
                        "maintainer-request",
                        "--reference",
                        "https://github.com/example/project/issues/2",
                        "--published",
                        "--output",
                        str(signal_path),
                        "--json",
                    ]
                )
            with redirect_stdout(io.StringIO()):
                validation_code = main(["signal", "validate", str(signal_path), "--json"])
            with redirect_stdout(io.StringIO()):
                readiness_code = main(["signal", "validate", str(signal_path), "--require-confirmed", "--json"])

            self.assertEqual(init_code, 0)
            self.assertEqual(validation_code, 0)
            self.assertEqual(readiness_code, 1)

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

    def test_uncertain_remote_write_does_not_retry_create(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            body_path = root / "body.md"
            packet = valid_packet()
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
            args = [
                "remote", "create", "--packet", str(packet_path), "--repo", "example/project", "--kind", "issue",
                "--title", packet["narrative"]["title"], "--body-file", str(body_path), "--confirm-operation-id", "", "--json",
            ]
            plan_output = io.StringIO()
            with redirect_stdout(plan_output):
                main(["remote", "plan", *args[2:-3], "--json"])
            operation_id = json.loads(plan_output.getvalue())["operation_id"]
            args[args.index("--confirm-operation-id") + 1] = operation_id
            fake_client = unittest.mock.MagicMock()
            fake_client.find_existing.return_value = []
            fake_client.create.return_value = "https://github.com/example/project/issues/7"

            with patch("reviewworthy.cli.GhClient", return_value=fake_client), patch(
                "reviewworthy.cli.save_operation_receipt", side_effect=GhError("receipt failure")
            ):
                with redirect_stdout(io.StringIO()):
                    first_code = main(args)
                with redirect_stdout(io.StringIO()):
                    second_code = main(args)

            receipt_path = root / "local" / "operations" / f"{operation_id}.json"
            self.assertEqual(first_code, 2)
            self.assertEqual(second_code, 2)
            self.assertEqual(fake_client.create.call_count, 1)
            self.assertEqual(json.loads(receipt_path.read_text())["status"], "pending")
