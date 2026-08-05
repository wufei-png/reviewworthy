from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest

from reviewworthy.github import GhClient, GhError, build_operation, load_operation_receipt, operation_receipt_path, save_operation_receipt

from helpers import valid_packet


class GitHubOperationTests(unittest.TestCase):
    def test_operation_marker_and_id_are_stable_for_same_rendered_request(self) -> None:
        packet = valid_packet()
        first = build_operation(packet, "example/project", "pull_request", "Fix input", "Body", "main", "fix/input")
        second = build_operation(packet, "example/project", "pull_request", "Fix input", "Body", "main", "fix/input")
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertIn(first.marker, first.body)
        self.assertEqual(first.permissions, ("contents:read", "pull-requests:write"))

    def test_changed_body_changes_confirmation_id(self) -> None:
        packet = valid_packet()
        first = build_operation(packet, "example/project", "issue", "Fix input", "Body")
        second = build_operation(packet, "example/project", "issue", "Fix input", "Changed Body")
        self.assertNotEqual(first.operation_id, second.operation_id)

    def test_operation_requires_pr_head(self) -> None:
        with self.assertRaises(ValueError):
            build_operation(valid_packet(), "example/project", "pull_request", "Fix", "Body")

    def test_policy_required_draft_is_part_of_operation_and_gh_command(self) -> None:
        packet = valid_packet()
        packet["policy"]["authoritative_claims"]["draft_pr_required"] = True
        operation = build_operation(packet, "example/project", "pull_request", "Fix", "Body", "main", "fix/input")
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            return CompletedProcess(argv, 0, "https://github.com/example/project/pull/7\n", "")

        self.assertTrue(operation.draft)
        GhClient(fake_runner).create(operation)
        self.assertIn("--draft", calls[0])

    def test_candidate_search_is_read_only_and_normalizes_issue_and_pr_kind(self) -> None:
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            current_kind = argv[1]
            body = [{"number": 1, "url": "https://github.com/example/project/issues/1", "title": "Same", "body": "", "state": "OPEN"}]
            return CompletedProcess(argv, 0, json.dumps(body), "")

        matches = GhClient(fake_runner).search_candidates("example/project", "same", "both")
        self.assertEqual({match["kind"] for match in matches}, {"issue", "pull_request"})
        self.assertEqual(len(calls), 2)

    def test_find_existing_reads_all_pages_and_filters_issue_kind(self) -> None:
        packet = valid_packet()
        operation = build_operation(packet, "example/project", "issue", "Fix input", "Body")
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            pages = [
                [{"number": 1, "html_url": "https://github.com/example/project/issues/1", "title": "Other", "body": "", "state": "open"}],
                [
                    {"number": 2, "html_url": "https://github.com/example/project/issues/2", "title": "Existing", "body": operation.marker, "state": "open"},
                    {"number": 3, "html_url": "https://github.com/example/project/pull/3", "title": "PR", "body": operation.marker, "state": "open", "pull_request": {}},
                ],
            ]
            return CompletedProcess(argv, 0, json.dumps(pages), "")

        matches = GhClient(fake_runner).find_existing(operation)

        self.assertEqual([match["number"] for match in matches], [2])
        self.assertIn("--paginate", calls[0])
        self.assertIn("--slurp", calls[0])

    def test_operation_receipt_round_trip(self) -> None:
        operation = build_operation(valid_packet(), "example/project", "issue", "Fix input", "Body", "main")
        with tempfile.TemporaryDirectory() as directory:
            path = operation_receipt_path(Path(directory) / ".reviewworthy" / "contribution.json", operation.operation_id)
            save_operation_receipt(path, operation, "https://github.com/example/project/issues/7")
            receipt = load_operation_receipt(path, operation)
            self.assertEqual(receipt["remote"], "https://github.com/example/project/issues/7")

    def test_incomplete_operation_receipt_requires_reconciliation(self) -> None:
        operation = build_operation(valid_packet(), "example/project", "issue", "Fix input", "Body", "main")
        with tempfile.TemporaryDirectory() as directory:
            path = operation_receipt_path(Path(directory) / ".reviewworthy" / "contribution.json", operation.operation_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "operation_id": operation.operation_id,
                "marker": operation.marker,
                "repo": operation.repo,
                "kind": operation.kind,
                "operation": operation.as_dict(),
                "status": "succeeded",
                "recorded_at": "2026-08-06T00:00:00Z",
            }), encoding="utf-8")

            with self.assertRaises(GhError):
                load_operation_receipt(path, operation)
