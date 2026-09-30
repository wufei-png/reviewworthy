from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from reviewworthy.cli import main
from reviewworthy.github import (
    GhClient, GhError, build_operation, save_operation_pending,
    save_operation_receipt, save_operation_pr_created,
)
from helpers import valid_packet


class RemoteRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "operation.json"
        self.packet = valid_packet()
        self.operation = build_operation(self.packet, "example/project", "issue", "Fix", "Body  ")
        self.url = "https://github.com/example/project/issues/7"
        self.client = MagicMock(spec=GhClient)
        self.client.find_existing.return_value = [{"url": self.url}]
        self.set_live()

    def set_live(self) -> None:
        self.client.read_operation_object.return_value = {
            "html_url": self.url, "title": self.operation.title, "body": self.operation.body,
            "head": {"sha": self.operation.head_sha}, "base": {"ref": self.operation.base},
            "draft": self.operation.draft,
        }
        self.client.pull_request_head.return_value = self.operation.head_sha

    def run_cli(self, extra: list[str] | None = None) -> tuple[int, dict]:
        output = io.StringIO()
        with patch("reviewworthy.cli.GhClient", return_value=self.client), redirect_stdout(output):
            code = main(["remote", "reconcile", "--state", str(self.state), "--json", *(extra or [])])
        self.client.create.assert_not_called()
        return code, json.loads(output.getvalue())

    def test_pending_remote_success_is_repaired_without_packet_or_body_inputs(self) -> None:
        save_operation_pending(self.state, self.operation)
        code, result = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(result["remote"], self.url)
        self.assertEqual(json.loads(self.state.read_text())["status"], "succeeded")
        self.client.verify_repository_identity.assert_called_once_with("example/project", 101)
        self.client.add_issue_note.assert_not_called()

    def test_known_url_survives_list_delay_and_drift_is_not_repaired_publicly(self) -> None:
        save_operation_receipt(self.state, self.operation, self.url)
        self.client.find_existing.return_value = []
        code, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.client.read_operation_object.assert_called_with(self.operation, self.url)
        for body, expected in (("edited", "remote_marker_missing"), (self.operation.body + "edited", "remote_payload_drift")):
            with self.subTest(body=body):
                self.client.read_operation_object.return_value["body"] = body
                code, result = self.run_cli()
                self.assertEqual(code, 1)
                self.assertIn(expected, {d["code"] for d in result["diagnostics"]})
                self.assertEqual(result["remote"], self.url)
        self.client.add_issue_note.assert_not_called()

    def test_zero_multiple_and_unavailable_marker_results_fail_closed(self) -> None:
        for matches, expected in (([], "remote_marker_not_found"), ([{"url": self.url}, {"url": self.url.replace("7", "8")}], "remote_marker_ambiguous")):
            with self.subTest(matches=matches):
                save_operation_pending(self.state, self.operation)
                self.client.find_existing.return_value = matches
                code, result = self.run_cli()
                self.assertEqual(code, 1)
                self.assertIn(expected, {d["code"] for d in result["diagnostics"]})
                self.assertEqual(json.loads(self.state.read_text())["status"], "pending")
                if matches:
                    self.assertEqual(len(result["matches"]), 2)
        save_operation_pending(self.state, self.operation)
        self.client.find_existing.side_effect = GhError("offline")
        self.assertEqual(self.run_cli()[0], 1)

    def prepare_pr(self) -> None:
        self.packet["basis"].update({"kind": "issue", "references": ["https://github.com/example/project/issues/1"]})
        self.operation = build_operation(self.packet, "example/project", "pull_request", "Fix", "Body", "main", "fix", self.packet["diff"])
        self.url = "https://github.com/example/project/pull/8"
        self.client.find_existing.return_value = [{"url": self.url}]
        self.client.find_issue_link_note.return_value = []
        self.client.issue_commentability.return_value = {"commentable": True}
        self.set_live()
        save_operation_pr_created(self.state, self.operation, self.url)

    def test_pr_note_requires_original_confirmation_and_existing_note_is_never_reposted(self) -> None:
        self.prepare_pr()
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(result["reason"], "issue_note_confirmation_required")
        self.client.add_issue_note.assert_not_called()
        self.assertEqual(self.run_cli(["--confirm-operation-id", "wrong"])[0], 2)
        self.client.add_issue_note.assert_not_called()
        code, _ = self.run_cli(["--confirm-operation-id", self.operation.operation_id])
        self.assertEqual(code, 0)
        self.client.add_issue_note.assert_called_once_with(self.operation.issue_url, self.url)
        self.client.find_issue_link_note.return_value = [{"id": 1}]
        self.assertEqual(self.run_cli()[0], 0)
        self.assertEqual(self.client.add_issue_note.call_count, 1)

    def test_pr_head_marker_and_comment_uncertainty_do_not_write_again(self) -> None:
        for mode in ("head", "locked", "comments", "write", "recheck"):
            with self.subTest(mode=mode):
                self.client.reset_mock(side_effect=True)
                self.prepare_pr()
                if mode == "head":
                    self.client.read_operation_object.return_value["head"]["sha"] = "other"
                elif mode == "locked":
                    self.client.issue_commentability.return_value = {"commentable": False, "reason": "issue_locked"}
                elif mode == "comments":
                    self.client.find_issue_link_note.side_effect = GhError("comments unavailable")
                elif mode == "write":
                    self.client.add_issue_note.side_effect = GhError("uncertain POST")
                else:
                    self.client.pull_request_head.return_value = "moved"
                code, _ = self.run_cli(["--confirm-operation-id", self.operation.operation_id])
                self.assertEqual(code, 1)
                self.assertEqual(self.client.add_issue_note.call_count, 1 if mode == "write" else 0)
                self.client.find_issue_link_note.side_effect = None
                self.client.add_issue_note.side_effect = None

    def test_invalid_unreadable_and_repository_mismatch_stop_before_mutation(self) -> None:
        self.state.write_text("[]")
        self.assertEqual(self.run_cli()[0], 2)
        self.client.verify_repository_identity.assert_not_called()
        save_operation_pending(self.state, self.operation)
        self.client.verify_repository_identity.side_effect = GhError("identity mismatch")
        self.assertEqual(self.run_cli()[0], 2)
        self.client.find_existing.assert_not_called()
