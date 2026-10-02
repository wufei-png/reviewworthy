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
from helpers import configure_created_object, valid_packet


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

    def test_existing_current_issue_state_retains_optional_ref_inputs(self) -> None:
        self.operation = build_operation(self.packet, "example/project", "issue", "Fix", "Body", "main", "feature")
        self.set_live()
        save_operation_pending(self.state, self.operation)
        code, result = self.run_cli()
        self.assertEqual(code, 0, result)
        retained = json.loads(self.state.read_text())
        self.assertEqual(retained["operation"], self.operation.as_dict())
        self.assertEqual(retained["status"], "succeeded")

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

    def test_historical_quoted_diff_paths_recover_without_recomputing_or_rendering(self) -> None:
        self.packet["diff"]["changed_files"] = ['"src/quoted\\tname.py"']
        self.prepare_pr()
        retained = json.loads(self.state.read_text())
        self.client.find_issue_link_note.return_value = [{"id": 1}]
        with patch("reviewworthy.cli.capture_pr_diff", side_effect=AssertionError("must not recapture historical Diff")), patch("reviewworthy.cli.build_operation", side_effect=AssertionError("must not render historical operation")):
            self.assertEqual(self.run_cli()[0], 0)
        self.assertEqual(json.loads(self.state.read_text())["operation_id"], retained["operation_id"])
        self.client.add_issue_note.assert_not_called()

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


class SignalRecoveryTests(unittest.TestCase):
    def test_signal_artifact_write_failure_is_recovered_and_edited_targets_are_preserved(self) -> None:
        from reviewworthy.signal import skeleton_signal
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            signal = skeleton_signal()
            source = root / "signal.json"
            source.write_text(json.dumps(signal))
            body = root / "body.md"
            body.write_text("Publish this evidence  \n")
            common = [str(source), "--repo", "example/project", "--repository-id", "101", "--title", "Bug", "--body-file", str(body)]
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["signal", "publish", "plan", *common, "--json"]), 0)
            plan = json.loads(output.getvalue())
            client = MagicMock(spec=GhClient)
            url = "https://github.com/example/project/issues/9"
            client.create.return_value = url
            client.find_existing.return_value = []
            with patch("reviewworthy.cli.GhClient", return_value=client), patch("reviewworthy.cli._replace_json", side_effect=OSError("artifact failure")), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["signal", "publish", "create", *common, "--confirm-operation-id", plan["operation_id"], "--json"]), 2)
            state = root / "local/v0.3/operations" / (plan["operation_id"] + ".json")
            self.assertEqual(json.loads(state.read_text())["status"], "succeeded")
            client.find_existing.return_value = [{"url": url}]
            client.read_operation_object.return_value = {"title": plan["title"], "body": plan["body"]}
            reconcile = ["signal", "publish", "reconcile", str(source), "--state", str(state), "--json"]
            edited = {**signal, "evidence": ["new unrelated evidence"]}
            source.write_text(json.dumps(edited))
            with patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(io.StringIO()):
                self.assertEqual(main(reconcile), 2)
            self.assertEqual(json.loads(source.read_text()), edited)
            source.write_text(json.dumps(signal))
            with patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(io.StringIO()):
                self.assertEqual(main(reconcile), 0)
                self.assertEqual(main(reconcile), 0)
            updated = json.loads(source.read_text())
            self.assertEqual(updated["reference"], url)
            self.assertEqual(updated["publication"]["body"], body.read_text())
            self.assertEqual(updated["lifecycle"], "pending")
            self.assertEqual(updated["authority"], signal["authority"])
            self.assertEqual(client.create.call_count, 1)
            client.add_issue_note.assert_not_called()
            wrong = root / "wrong.json"
            wrong.write_text(json.dumps(signal))
            with patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["signal", "publish", "reconcile", str(wrong), "--state", str(state), "--json"]), 2)

    def test_original_current_record_without_snapshot_can_recover_matching_subject(self) -> None:
        from reviewworthy.github import build_signal_operation
        from reviewworthy.signal import skeleton_signal
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "signal.json"
            signal = skeleton_signal(reference="local-draft-1")
            source.write_text(json.dumps(signal))
            operation = build_signal_operation(signal, "example/project", "Bug", "Body  ", 101)
            state = root / "state.json"
            save_operation_pending(state, operation)
            client = MagicMock(spec=GhClient)
            client.find_existing.return_value = [{"url": "https://github.com/example/project/issues/9"}]
            client.read_operation_object.return_value = {"title": operation.title, "body": operation.body}
            args = ["signal", "publish", "reconcile", str(source), "--state", str(state), "--json"]
            # Legacy current state has no original full Signal snapshot; only the
            # stable subject and recorded publication inputs can be compared.
            signal["reference"] = "different-draft"
            source.write_text(json.dumps(signal))
            with patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 2)
            signal["reference"] = "local-draft-1"
            source.write_text(json.dumps(signal))
            # A pre-publication Issue draft must have no public reference.
            # Use a valid empty-reference subject for this existing state case.
            signal["reference"] = ""
            source.write_text(json.dumps(signal))
            operation = build_signal_operation(signal, "example/project", "Bug", "Body  ", 101)
            save_operation_pending(state, operation)
            client.read_operation_object.return_value = {"title": operation.title, "body": operation.body}
            with patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)

    def test_legacy_published_signal_preserves_exact_body_and_original_retry_inputs(self) -> None:
        from reviewworthy.github import build_signal_operation
        from reviewworthy.signal import skeleton_signal
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "signal.json"
            body_path = root / "body.md"
            body = "Body  \n"
            body_path.write_text(body)
            signal = skeleton_signal()
            operation = build_signal_operation(signal, "example/project", "Bug", body, 101)
            state = root / "local/v0.3/operations" / (operation.operation_id + ".json")
            url = "https://github.com/example/project/issues/9"
            save_operation_receipt(state, operation, url)
            publication = {"operation_id": operation.operation_id, "repo": operation.repo, "title": operation.title, "body": body}
            signal.update({"reference": url, "publication_subject_id": operation.subject_id, "publication": publication})
            source.write_text(json.dumps(signal))
            client = MagicMock(spec=GhClient)
            client.find_existing.return_value = [{"url": url}]
            client.read_operation_object.return_value = {"title": operation.title, "body": operation.body}
            with patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["signal", "publish", "reconcile", str(source), "--state", str(state), "--json"]), 0)
                self.assertEqual(main(["signal", "publish", "create", str(source), "--repo", "example/project", "--repository-id", "101", "--title", operation.title, "--body-file", str(body_path), "--confirm-operation-id", operation.operation_id, "--json"]), 0)
            self.assertEqual(json.loads(source.read_text())["publication"], publication)
            client.create.assert_not_called()

    def test_signal_target_changes_during_remote_inspection_are_never_overwritten(self) -> None:
        from reviewworthy.github import build_signal_operation
        from reviewworthy.signal import skeleton_signal
        for mode in ("edited", "deleted", "newly_created"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "signal.json"
                signal = skeleton_signal()
                if mode != "newly_created":
                    source.write_text(json.dumps(signal))
                operation = build_signal_operation(signal, "example/project", "Bug", "Body", 101)
                state = root / "state.json"
                save_operation_pending(state, operation, signal_recovery={"target": str(source.resolve()), "input": signal, "body": "Body"})
                edited = {**signal, "evidence": ["new human evidence"]}
                client = MagicMock(spec=GhClient)
                client.find_existing.return_value = [{"url": "https://github.com/example/project/issues/9"}]

                def inspect(*args):
                    if mode == "deleted":
                        source.unlink()
                    else:
                        source.write_text(json.dumps(edited))
                    return {"title": operation.title, "body": operation.body}

                client.read_operation_object.side_effect = inspect
                output = io.StringIO()
                with patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(output):
                    self.assertEqual(main(["signal", "publish", "reconcile", str(source), "--state", str(state), "--json"]), 2)
                self.assertIn("changed during remote inspection", json.loads(output.getvalue())["error"])
                if mode == "deleted":
                    self.assertFalse(source.exists())
                else:
                    self.assertEqual(json.loads(source.read_text()), edited)
                self.assertEqual(json.loads(state.read_text())["status"], "succeeded")
                client.create.assert_not_called()

    def test_missing_original_signal_output_is_restored_from_saved_input(self) -> None:
        from reviewworthy.github import build_signal_operation
        from reviewworthy.signal import skeleton_signal
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "published.json"
            signal = skeleton_signal()
            operation = build_signal_operation(signal, "example/project", "Bug", "Body", 101)
            state = root / "state.json"
            recovery = {"target": str(target.resolve()), "input": signal, "body": "Body"}
            save_operation_pending(state, operation, signal_recovery=recovery)
            client = MagicMock(spec=GhClient)
            client.find_existing.return_value = [{"url": "https://github.com/example/project/issues/9"}]
            client.read_operation_object.return_value = {"title": operation.title, "body": operation.body}
            with patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["signal", "publish", "reconcile", str(target), "--state", str(state), "--json"]), 0)
            self.assertEqual(json.loads(target.read_text())["reference"], "https://github.com/example/project/issues/9")
            client.create.assert_not_called()


class UncertainRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet = valid_packet()
        self.packet_path = self.root / "packet.json"
        self.packet_path.write_text(json.dumps(self.packet))
        self.body = self.root / "body.md"
        self.body.write_text(self.packet["narrative"]["body"])
        self.operation = build_operation(self.packet, "example/project", "issue", self.packet["narrative"]["title"], self.body.read_text(), "main")
        self.state = self.root / "local/v0.3/operations" / (self.operation.operation_id + ".json")
        self.args = ["remote", "create", "--packet", str(self.packet_path), "--repo", "example/project", "--kind", "issue", "--title", self.operation.title, "--body-file", str(self.body), "--confirm-operation-id", self.operation.operation_id, "--json"]
        self.url = "https://github.com/example/project/issues/7"
        self.client = MagicMock(spec=GhClient)
        self.client.find_existing.return_value = []
        self.client.create.return_value = self.url
        configure_created_object(self.client)

    def run_cli(self, retry: bool = True) -> tuple[int, dict]:
        output = io.StringIO()
        with patch("reviewworthy.cli.GhClient", return_value=self.client), redirect_stdout(output):
            code = main(self.args + (["--retry-uncertain"] if retry else []))
        return code, json.loads(output.getvalue())

    def test_retry_requires_valid_pending_state_and_default_still_refuses(self) -> None:
        self.assertEqual(self.run_cli()[0], 2)
        save_operation_pending(self.state, self.operation)
        self.assertEqual(self.run_cli(False)[0], 2)
        self.client.create.assert_not_called()
        code, result = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("residual duplicate risk", result["retry_warning"])
        self.client.create.assert_called_once_with(self.operation)
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.client.create.call_count, 1)

    def test_issue_create_with_head_records_success_and_immediate_retry_reuses_it(self) -> None:
        self.operation = build_operation(self.packet, "example/project", "issue", self.packet["narrative"]["title"],
                                         self.body.read_text(), "main", "feature")
        self.state = self.root / "local/v0.3/operations" / (self.operation.operation_id + ".json")
        self.args[self.args.index("--confirm-operation-id") + 1] = self.operation.operation_id
        self.args.extend(["--head", "feature"])
        code, result = self.run_cli(False)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["outcome"], "created")
        self.assertEqual(json.loads(self.state.read_text())["status"], "succeeded")
        code, result = self.run_cli(False)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["source"], "local_receipt")
        self.client.create.assert_called_once_with(self.operation)

    def test_appearing_match_is_reconciled_and_multiple_matches_block(self) -> None:
        save_operation_pending(self.state, self.operation)
        self.client.find_existing.side_effect = None
        self.client.find_existing.return_value = [{"url": self.url}]
        self.assertEqual(self.run_cli()[0], 0)
        self.client.create.assert_not_called()
        save_operation_pending(self.state, self.operation)
        self.client.find_existing.return_value = [{"url": self.url}, {"url": self.url.replace("7", "8")}]
        self.assertEqual(self.run_cli()[0], 2)
        self.client.create.assert_not_called()

    def test_another_uncertain_write_preserves_pending_and_known_or_invalid_state_never_retries(self) -> None:
        save_operation_pending(self.state, self.operation)
        self.client.create.side_effect = GhError("network result uncertain")
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(json.loads(self.state.read_text())["status"], "pending")
        self.assertEqual(self.client.create.call_count, 1)
        record = json.loads(self.state.read_text())
        record["known_remote"] = self.url
        self.state.write_text(json.dumps(record))
        self.assertEqual(self.run_cli()[0], 2)
        record["known_remote"] = "bad-url"
        self.state.write_text(json.dumps(record))
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.client.create.call_count, 1)

    def test_current_readiness_and_confirmation_cannot_be_bypassed(self) -> None:
        save_operation_pending(self.state, self.operation)
        self.args[self.args.index("--confirm-operation-id") + 1] = "wrong"
        self.assertEqual(self.run_cli()[0], 2)
        self.client.create.assert_not_called()
        self.args[self.args.index("--confirm-operation-id") + 1] = self.operation.operation_id
        self.packet["contract"]["approval"]["status"] = "pending"
        self.packet_path.write_text(json.dumps(self.packet))
        self.assertEqual(self.run_cli()[0], 1)
        self.client.create.assert_not_called()

    def test_signal_retry_preserves_original_inputs_and_attempts_only_once(self) -> None:
        from reviewworthy.github import build_signal_operation
        from reviewworthy.signal import skeleton_signal
        signal = skeleton_signal()
        source = self.root / "signal.json"
        source.write_text(json.dumps(signal))
        self.operation = build_signal_operation(signal, "example/project", "Bug", "Body", 101)
        self.body.write_text("Body")
        self.state = self.root / "local/v0.3/operations" / (self.operation.operation_id + ".json")
        recovery = {"target": str(source.resolve()), "input": signal, "body": "Body"}
        save_operation_pending(self.state, self.operation, signal_recovery=recovery)
        self.args = ["signal", "publish", "create", str(source), "--repo", "example/project", "--repository-id", "101", "--title", "Bug", "--body-file", str(self.body), "--confirm-operation-id", self.operation.operation_id, "--json"]
        edited = {**signal, "evidence": ["edited"]}
        source.write_text(json.dumps(edited))
        self.assertEqual(self.run_cli()[0], 2)
        self.client.create.assert_not_called()
        source.write_text(json.dumps(signal))
        self.assertEqual(self.run_cli()[0], 0)
        self.client.create.assert_called_once_with(self.operation)

    def test_post_create_zero_and_unavailable_lists_keep_known_success_for_historical_retry(self) -> None:
        for post_result in ([], GhError("list unavailable")):
            with self.subTest(post_result=post_result):
                self.state.unlink(missing_ok=True)
                save_operation_pending(self.state, self.operation)
                self.client.create.reset_mock()
                self.client.find_existing.side_effect = [[], post_result]
                code, result = self.run_cli()
                self.assertEqual(code, 1)
                self.assertEqual(result["remote"], self.url)
                self.assertEqual(result["inspection"]["outcome"], "needs_reconciliation")
                record = json.loads(self.state.read_text())
                self.assertEqual(record["status"], "succeeded")
                self.assertEqual(record["known_remote"], self.url)
                code, historical = self.run_cli(False)
                self.assertEqual(code, 0)
                self.assertEqual(historical["source"], "local_receipt")
                self.assertEqual(self.client.create.call_count, 1)

    def test_post_create_duplicate_race_reports_all_urls_and_never_creates_again(self) -> None:
        save_operation_pending(self.state, self.operation)
        duplicate = self.url.replace("7", "8")
        self.client.find_existing.side_effect = [[], [{"url": self.url}, {"url": duplicate}]]
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(result["inspection"]["matches"], [self.url, duplicate])
        self.assertEqual(self.client.find_existing.call_count, 2)
        self.assertEqual(self.client.create.call_count, 1)
        self.client.add_issue_note.assert_not_called()
        self.assertEqual(json.loads(self.state.read_text())["remote"], self.url)

    def test_post_create_receipt_failure_preserves_known_url_for_recovery(self) -> None:
        save_operation_pending(self.state, self.operation)
        with patch("reviewworthy.cli.save_operation_receipt", side_effect=GhError("disk unavailable")):
            self.assertEqual(self.run_cli()[0], 2)
        record = json.loads(self.state.read_text())
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["known_remote"], self.url)
        self.client.find_existing.side_effect = None
        self.client.find_existing.return_value = []
        with patch("reviewworthy.cli.GhClient", return_value=self.client), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["remote", "reconcile", "--state", str(self.state), "--json"]), 0)
        self.assertEqual(self.client.create.call_count, 1)

    def test_post_create_pr_duplicate_or_drift_prevents_issue_note(self) -> None:
        for mode in ("duplicates", "head", "body", "list"):
            with self.subTest(mode=mode):
                operation = build_operation(self.packet, "example/project", "pull_request", self.packet["narrative"]["title"], self.body.read_text(), "main", "fix", self.packet["diff"])
                state = self.root / "local/v0.3/operations" / (operation.operation_id + ".json")
                state.unlink(missing_ok=True)
                save_operation_pending(state, operation)
                client = MagicMock(spec=GhClient)
                url = "https://github.com/example/project/pull/8"
                client.create.return_value = url
                configure_created_object(client)
                if mode == "duplicates":
                    client.find_existing.side_effect = [[], [{"url": url}, {"url": url.replace("8", "9")}]]
                elif mode == "list":
                    client.find_existing.side_effect = [[], GhError("offline")]
                else:
                    live = {"title": operation.title, "body": operation.body, "head": {"sha": operation.head_sha}, "base": {"ref": operation.base}, "draft": operation.draft}
                    if mode == "head":
                        live["head"]["sha"] = "moved"
                    else:
                        live["body"] = "edited"
                    client.read_operation_object.side_effect = None
                    client.read_operation_object.return_value = live
                    client.find_existing.return_value = []
                client.verify_public_reference.return_value = self.packet["basis"]["verification"] | {"verified": True}
                args = ["remote", "create", "--packet", str(self.packet_path), "--repo", "example/project", "--kind", "pull_request", "--title", operation.title, "--body-file", str(self.body), "--head", "fix", "--confirm-operation-id", operation.operation_id, "--retry-uncertain", "--json"]
                with patch("reviewworthy.cli.capture_pr_diff", return_value=self.packet["diff"]), patch("reviewworthy.cli.GhClient", return_value=client), redirect_stdout(io.StringIO()):
                    self.assertEqual(main(args), 1)
                self.assertEqual(json.loads(state.read_text())["status"], "needs_reconciliation")
                client.add_issue_note.assert_not_called()
                self.assertEqual(client.create.call_count, 1)
