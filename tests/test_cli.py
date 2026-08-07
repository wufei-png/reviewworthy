from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reviewworthy.cli import main
from reviewworthy.git import current_head
from reviewworthy.github import GhError
from reviewworthy.packet import material_snapshot, skeleton_packet

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

    def test_signal_verify_is_read_only_and_signal_publish_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            signal_path = root / "signal.json"
            signal_path.write_text(json.dumps({
                "signal_version": "0.1",
                "kind": "maintainer-request",
                "reference": "",
                "status": "pending",
                "evidence": [],
                "published": False,
                "confirmed_by": "",
                "confirmed_at": "",
            }), encoding="utf-8")
            body_path = root / "body.md"
            body_path.write_text("Please review this candidate.\n", encoding="utf-8")
            published_path = root / "published" / "signal.json"
            plan_output = io.StringIO()
            plan_args = [
                "signal", "publish", "plan", str(signal_path), "--repo", "example/project",
                "--title", "Candidate request", "--body-file", str(body_path), "--json",
            ]
            with redirect_stdout(plan_output):
                plan_code = main(plan_args)
            operation_id = json.loads(plan_output.getvalue())["operation_id"]
            create_args = [
                "signal", "publish", "create", str(signal_path), "--repo", "example/project",
                "--title", "Candidate request", "--body-file", str(body_path),
                "--confirm-operation-id", operation_id, "--output", str(published_path), "--json",
            ]
            fake_client = unittest.mock.MagicMock()
            fake_client.find_existing.return_value = []
            fake_client.create.return_value = "https://github.com/example/project/issues/9"
            with patch("reviewworthy.cli.GhClient", return_value=fake_client):
                with redirect_stdout(io.StringIO()):
                    first_code = main(create_args)
                retry_args = [
                    "signal", "publish", "create", str(published_path), "--repo", "example/project",
                    "--title", "Candidate request", "--body-file", str(body_path),
                    "--confirm-operation-id", operation_id, "--json",
                ]
                with redirect_stdout(io.StringIO()):
                    second_code = main(retry_args)
                with redirect_stdout(io.StringIO()):
                    third_code = main(create_args)

            published = json.loads(published_path.read_text())
            self.assertEqual(plan_code, 0)
            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertEqual(third_code, 0)
            self.assertTrue(published["published"])
            self.assertEqual(published["reference"], "https://github.com/example/project/issues/9")
            self.assertEqual(fake_client.create.call_count, 1)

    def test_signal_verify_checks_github_reference_without_mutating_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            signal_path = Path(directory) / "signal.json"
            signal = {
                "signal_version": "0.1",
                "kind": "issue",
                "reference": "https://github.com/example/project/issues/2",
                "status": "pending",
                "evidence": [],
                "published": True,
                "confirmed_by": "",
                "confirmed_at": "",
            }
            signal_path.write_text(json.dumps(signal), encoding="utf-8")
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {"verified": True, "provider": "github", "url": signal["reference"]}
            output = io.StringIO()
            with patch("reviewworthy.cli.GhClient", return_value=fake_client), redirect_stdout(output):
                code = main(["signal", "verify", str(signal_path), "--json"])

            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output.getvalue())["valid"])
            self.assertEqual(json.loads(signal_path.read_text()), signal)

    def test_signal_verify_can_explicitly_record_successful_public_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            signal_path = Path(directory) / "signal.json"
            signal = {
                "signal_version": "0.1",
                "kind": "issue",
                "reference": "https://github.com/example/project/issues/2",
                "status": "pending",
                "evidence": [],
                "published": True,
                "confirmed_by": "",
                "confirmed_at": "",
            }
            signal_path.write_text(json.dumps(signal), encoding="utf-8")
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {
                "verified": True,
                "provider": "github",
                "repository": "example/project",
                "record_type": "issue",
                "number": 2,
                "url": signal["reference"],
                "visibility": "public",
            }
            with patch("reviewworthy.cli.GhClient", return_value=fake_client), redirect_stdout(io.StringIO()):
                code = main(["signal", "verify", str(signal_path), "--record", "--json"])

            recorded = json.loads(signal_path.read_text())
            self.assertEqual(code, 0)
            self.assertEqual(recorded["verification"]["status"], "verified")
            self.assertEqual(recorded["verification"]["reference"], signal["reference"])

    def test_candidate_select_bind_and_understanding_record_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            menu_path = root / "menu.json"
            menu_path.write_text(json.dumps({
                "menu_version": "0.1",
                "repository": "example/project",
                "project_brief": "brief.json",
                "candidates": [{
                    "id": "candidate-001",
                    "title": "Narrow fix",
                    "basis": {"kind": "issue", "references": ["https://github.com/example/project/issues/1"], "evidence": []},
                    "duplicate_search": {"checked": True, "matches": []},
                    "value": {"summary": "Fixes a regression"},
                    "scope": {"files": ["src/example.py"]},
                    "review_cost": "small",
                    "verifiability": "high",
                    "risk": [],
                    "recommendation": "plan_directly",
                }],
                "selection": {"selected_id": "", "confirmed": False},
            }), encoding="utf-8")
            packet_path = root / "packet.json"
            packet_path.write_text(json.dumps(skeleton_packet("contribution-001", "issue-backed")), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                select_code = main(["candidate", "select", str(menu_path), "--candidate-id", "candidate-001", "--confirm", "--json"])
                bind_code = main(["candidate", "bind", "--menu", str(menu_path), "--packet", str(packet_path), "--json"])
                orientation_code = main([
                    "understanding", "record", str(packet_path), "--phase", "orientation", "--status", "passed",
                    "--summary", "Explained the material.", "--topic", "contract", "--topic", "diff",
                    "--topic", "verification", "--topic", "policy", "--json",
                ])
                assessment_code = main([
                    "understanding", "record", str(packet_path), "--phase", "assessment", "--status", "passed",
                    "--question", "What changed?", "--answer", "The selected boundary changed.", "--json",
                ])
                validate_code = main(["understanding", "validate", str(packet_path), "--json"])

            bound = json.loads(packet_path.read_text())
            self.assertEqual(select_code, 0)
            self.assertEqual(bind_code, 0)
            self.assertEqual(orientation_code, 0)
            self.assertEqual(assessment_code, 0)
            self.assertEqual(validate_code, 0)
            self.assertEqual(bound["candidate_selection"]["candidate_id"], "candidate-001")

    def test_action_can_mark_changed_file_evidence_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet_path.write_text(json.dumps(valid_packet()), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                code = main(["action", "check", str(packet_path), "--changed-files-unavailable", "--json"])

            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(any("Changed-file evidence was not provided" in unknown for unknown in result["unknowns"]))

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
                        "main",
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
                        "main",
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

    def test_pull_request_create_links_issue_once_and_reuses_linked_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root = Path(__file__).parents[1]
            head_sha = current_head(repository_root)
            packet = valid_packet()
            packet["repository"]["base_sha"] = head_sha
            packet["diff"].update({"base_sha": head_sha, "head_sha": head_sha})
            packet["verification"]["receipts"][0]["head_sha"] = head_sha
            packet["verification"]["receipts"][0]["cwd"] = str(repository_root)
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            packet_path = root / "packet.json"
            body_path = root / "body.md"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
            common = [
                "--packet", str(packet_path),
                "--repo", "example/project",
                "--kind", "pull_request",
                "--title", packet["narrative"]["title"],
                "--body-file", str(body_path),
                "--base", "main",
                "--head", "main",
                "--root", str(repository_root),
            ]
            plan_output = io.StringIO()
            with redirect_stdout(plan_output):
                self.assertEqual(main(["remote", "plan", *common, "--json"]), 0)
            operation_id = json.loads(plan_output.getvalue())["operation_id"]
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {
                "verified": True,
                "provider": "github",
                "repository": "example/project",
                "repository_id": 101,
                "record_type": "issue",
                "state": "open",
            }
            fake_client.find_existing.return_value = []
            fake_client.create.return_value = "https://github.com/example/project/pull/8"
            fake_client.find_issue_link_note.return_value = []
            fake_client.issue_commentability.return_value = {"commentable": True}
            fake_client.add_issue_note.return_value = {}
            create_args = ["remote", "create", *common, "--confirm-operation-id", operation_id, "--json"]
            with patch("reviewworthy.cli.GhClient", return_value=fake_client):
                with redirect_stdout(io.StringIO()):
                    first_code = main(create_args)
                with redirect_stdout(io.StringIO()):
                    second_code = main(create_args)

            receipt_files = list((root / "local" / "operations").glob("*.json"))
            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertEqual(len(receipt_files), 1)
            receipt = json.loads(receipt_files[0].read_text())
            self.assertEqual(receipt["status"], "linked")
            self.assertEqual(receipt["pr_url"], "https://github.com/example/project/pull/8")
            self.assertEqual(receipt["issue_url"], "https://github.com/example/project/issues/1")
            self.assertEqual(fake_client.create.call_count, 1)
            self.assertEqual(fake_client.add_issue_note.call_count, 1)

    def test_pull_request_link_failure_is_terminal_without_creating_another_pr(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root = Path(__file__).parents[1]
            head_sha = current_head(repository_root)
            packet = valid_packet()
            packet["repository"]["base_sha"] = head_sha
            packet["diff"].update({"base_sha": head_sha, "head_sha": head_sha})
            packet["verification"]["receipts"][0]["head_sha"] = head_sha
            packet["verification"]["receipts"][0]["cwd"] = str(repository_root)
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            packet_path = root / "packet.json"
            body_path = root / "body.md"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
            common = [
                "--packet", str(packet_path), "--repo", "example/project", "--kind", "pull_request",
                "--title", packet["narrative"]["title"], "--body-file", str(body_path), "--base", "main",
                "--head", "main", "--root", str(repository_root),
            ]
            plan_output = io.StringIO()
            with redirect_stdout(plan_output):
                main(["remote", "plan", *common, "--json"])
            operation_id = json.loads(plan_output.getvalue())["operation_id"]
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {"verified": True, "repository": "example/project", "repository_id": 101, "record_type": "issue"}
            fake_client.find_existing.return_value = []
            fake_client.create.return_value = "https://github.com/example/project/pull/9"
            fake_client.find_issue_link_note.side_effect = GhError("Issue comments unavailable")
            create_args = ["remote", "create", *common, "--confirm-operation-id", operation_id, "--json"]
            with patch("reviewworthy.cli.GhClient", return_value=fake_client):
                with redirect_stdout(io.StringIO()):
                    first_code = main(create_args)
                with redirect_stdout(io.StringIO()):
                    second_code = main(create_args)
            receipt_files = list((root / "local" / "operations").glob("*.json"))
            self.assertEqual(first_code, 1)
            self.assertEqual(second_code, 1)
            self.assertEqual(json.loads(receipt_files[0].read_text())["status"], "needs_reconciliation")
            self.assertEqual(fake_client.create.call_count, 1)
