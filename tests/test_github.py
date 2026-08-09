from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest

from reviewworthy.github import (
    GhClient,
    GhError,
    build_operation,
    build_signal_operation,
    load_operation_receipt,
    operation_lock,
    operation_receipt_path,
    save_operation_link_attempted,
    save_operation_linked,
    save_operation_needs_reconciliation,
    save_operation_pr_created,
    save_operation_receipt,
)

from helpers import valid_packet


class GitHubOperationTests(unittest.TestCase):
    def test_operation_marker_and_id_are_stable_for_same_rendered_request(self) -> None:
        packet = valid_packet()
        first = build_operation(packet, "example/project", "pull_request", "Fix input", "Body", "main", "fix/input", packet["diff"])
        second = build_operation(packet, "example/project", "pull_request", "Fix input", "Body", "main", "fix/input", packet["diff"])
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertIn(first.marker, first.body)
        self.assertEqual(first.permissions, ("contents:read", "pull-requests:write", "issues:write"))

    def test_repository_casing_does_not_change_operation_identity(self) -> None:
        packet = valid_packet()
        lower = build_operation(packet, "owner/repo", "issue", "Fix input", "Body")
        mixed = build_operation(packet, "Owner/Repo", "issue", "Fix input", "Body")

        self.assertEqual(lower.operation_id, mixed.operation_id)
        self.assertEqual(lower.marker, mixed.marker)
        self.assertEqual(mixed.repo, "owner/repo")

    def test_packet_03_issue_operation_uses_only_current_identity(self) -> None:
        packet = valid_packet()
        operation = build_operation(packet, "example/project", "issue", "Fix input", "Body")
        self.assertIn("reviewworthy:v0.3:operation-id", operation.marker)
        self.assertNotIn("base_sha", operation.as_dict())
        self.assertNotIn("merge_base_sha", operation.as_dict())
        self.assertIn("subject_digest", operation.as_dict())

    def test_pull_request_diff_identity_changes_confirmation_id(self) -> None:
        packet = valid_packet()
        baseline = build_operation(packet, "example/project", "pull_request", "Fix input", "Body", "main", "fix/input", packet["diff"])

        for field, value in (
            ("base_tip_sha", "other-base"),
            ("merge_base_sha", "other-merge-base"),
            ("head_sha", "other-head"),
            ("subject_digest", "other-subject"),
        ):
            changed = dict(packet["diff"])
            changed[field] = value
            operation = build_operation(packet, "example/project", "pull_request", "Fix input", "Body", "main", "fix/input", changed)
            self.assertNotEqual(operation.operation_id, baseline.operation_id, field)

    def test_changed_body_changes_confirmation_id(self) -> None:
        packet = valid_packet()
        first = build_operation(packet, "example/project", "issue", "Fix input", "Body")
        second = build_operation(packet, "example/project", "issue", "Fix input", "Changed Body")
        self.assertNotEqual(first.operation_id, second.operation_id)

    def test_operation_requires_pr_head(self) -> None:
        with self.assertRaises(ValueError):
            build_operation(valid_packet(), "example/project", "pull_request", "Fix", "Body")

    def test_signal_publication_operation_is_issue_write_and_stable_after_publication(self) -> None:
        signal = {"record_type": "issue", "claim_type": "maintainer_request", "reference": ""}
        first = build_signal_operation(signal, "example/project", "Request", "Body", 101)
        signal["reference"] = "https://github.com/example/project/issues/7"
        signal["publication_subject_id"] = first.subject_id
        second = build_signal_operation(signal, "example/project", "Request", "Body", 101)

        self.assertEqual(first.operation_id, second.operation_id)
        self.assertEqual(first.kind, "issue")
        self.assertEqual(first.permissions, ("issues:write",))
        self.assertEqual(first.purpose, "signal_publication")

        changed_repository = build_signal_operation(signal, "example/project", "Request", "Body", 202)
        self.assertNotEqual(changed_repository.operation_id, first.operation_id)

    def test_current_signal_receipt_shape_round_trips(self) -> None:
        operation = build_signal_operation(
            {"record_type": "issue", "claim_type": "maintainer_request", "reference": ""},
            "example/project", "Request", "Body", 101,
        )
        current_operation = operation.as_dict()
        self.assertNotIn("base_sha", current_operation)
        self.assertIn("subject_digest", current_operation)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps({
                "state_version": "0.3",
                "operation_id": operation.operation_id,
                "marker": operation.marker,
                "repo": operation.repo,
                "kind": operation.kind,
                "operation": current_operation,
                "status": "succeeded",
                "remote": "https://github.com/example/project/issues/7",
                "recorded_at": "2026-08-06T00:00:00Z",
            }), encoding="utf-8")

            self.assertEqual(load_operation_receipt(path, operation)["status"], "succeeded")

    def test_discussion_signal_cannot_be_silently_published_as_an_issue(self) -> None:
        with self.assertRaises(ValueError):
            build_signal_operation(
                {"record_type": "discussion", "claim_type": "accepted_proposal", "reference": ""},
                "example/project", "Request", "Body", 101,
            )

    def test_policy_required_draft_is_part_of_operation_and_gh_command(self) -> None:
        packet = valid_packet()
        packet["policy"]["authoritative_claims"]["draft_pr_required"] = True
        operation = build_operation(packet, "example/project", "pull_request", "Fix", "Body", "main", "fix/input", packet["diff"])
        calls = []
        bodies = []

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            body_path = Path(argv[argv.index("--body-file") + 1])
            bodies.append(body_path.read_text())
            return CompletedProcess(argv, 0, "https://github.com/example/project/pull/7\n", "")

        self.assertTrue(operation.draft)
        GhClient(fake_runner).create(operation)
        self.assertIn("--draft", calls[0])
        self.assertIn("--body-file", calls[0])
        self.assertNotIn(operation.body, calls[0])
        self.assertEqual(bodies, [operation.body])

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

    def test_verify_public_reference_uses_read_only_github_api(self) -> None:
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            if argv[2] == "repos/example/project":
                return CompletedProcess(argv, 0, json.dumps({"visibility": "public"}), "")
            return CompletedProcess(argv, 0, json.dumps({"html_url": "https://github.com/example/project/issues/2", "state": "open"}), "")

        result = GhClient(fake_runner).verify_public_reference("https://github.com/example/project/issues/2")

        self.assertTrue(result["verified"])
        self.assertEqual(result["record_type"], "issue")
        self.assertEqual(calls, [
            ["gh", "api", "repos/example/project", "--method", "GET"],
            ["gh", "api", "repos/example/project/issues/2", "--method", "GET"],
        ])

    def test_remote_write_repository_identity_requires_live_numeric_match(self) -> None:
        def fake_runner(argv, **kwargs):
            return CompletedProcess(
                argv,
                0,
                json.dumps({"id": 101, "full_name": "Example/Project", "visibility": "public"}),
                "",
            )

        identity = GhClient(fake_runner).verify_repository_identity("example/project", 101)
        self.assertEqual(identity["repository_id"], 101)

        with self.assertRaises(GhError):
            GhClient(fake_runner).verify_repository_identity("example/project", 202)

    def test_verify_discussion_uses_graphql_and_normalizes_current_record(self) -> None:
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            if argv[2] == "repos/example/project":
                return CompletedProcess(argv, 0, json.dumps({"visibility": "public", "id": 101}), "")
            return CompletedProcess(argv, 0, json.dumps({
                "data": {"repository": {"discussion": {
                    "number": 4,
                    "url": "https://github.com/example/project/discussions/4",
                    "title": "Proposal",
                    "closed": False,
                    "authorAssociation": "MEMBER",
                }}},
            }), "")

        result = GhClient(fake_runner).verify_public_reference(
            "https://github.com/example/project/discussions/4"
        )

        self.assertTrue(result["verified"])
        self.assertEqual(result["record_type"], "discussion")
        self.assertEqual(result["state"], "open")
        self.assertEqual(result["author_association"], "MEMBER")
        self.assertEqual(calls[1][1:3], ["api", "graphql"])
        self.assertIn("number=4", calls[1])

    def test_verify_public_reference_rejects_private_repository_and_noncanonical_record(self) -> None:
        def private_runner(argv, **kwargs):
            return CompletedProcess(argv, 0, json.dumps({"visibility": "private"}), "")

        private = GhClient(private_runner).verify_public_reference("https://github.com/example/project/issues/2")
        self.assertFalse(private["verified"])
        self.assertEqual(private["error"], "repository_not_public")

        def mismatch_runner(argv, **kwargs):
            if argv[2] == "repos/example/project":
                return CompletedProcess(argv, 0, json.dumps({"visibility": "public"}), "")
            return CompletedProcess(argv, 0, json.dumps({"html_url": "https://github.com/example/project/pull/2"}), "")

        mismatch = GhClient(mismatch_runner).verify_public_reference("https://github.com/example/project/issues/2")
        self.assertFalse(mismatch["verified"])
        self.assertEqual(mismatch["error"], "reference_canonical_mismatch")

    def test_verify_public_reference_rejects_query_and_fragment_decorations(self) -> None:
        with self.assertRaises(GhError):
            GhClient().verify_public_reference("https://github.com/example/project/issues/2?state=open")
        with self.assertRaises(GhError):
            GhClient().verify_public_reference("https://github.com/example/project/issues/2#details")

    def test_issue_commentability_normalizes_state_reason_and_duplicate_label(self) -> None:
        def client_for(record: dict):
            def fake_runner(argv, **kwargs):
                if argv[2] == "repos/example/project":
                    return CompletedProcess(argv, 0, json.dumps({"visibility": "public"}), "")
                return CompletedProcess(argv, 0, json.dumps({
                    "html_url": "https://github.com/example/project/issues/2",
                    "state": "closed",
                    **record,
                }), "")
            return GhClient(fake_runner)

        for state_reason in ("not_planned", "not-planned"):
            result = client_for({"state_reason": state_reason}).issue_commentability("https://github.com/example/project/issues/2")
            self.assertFalse(result["commentable"])
            self.assertEqual(result["reason"], "issue_not_planned")

        duplicate = client_for({"labels": [{"name": "Duplicate"}]}).issue_commentability("https://github.com/example/project/issues/2")
        self.assertFalse(duplicate["commentable"])
        self.assertEqual(duplicate["reason"], "issue_duplicate")

        reopened = client_for({"state_reason": "reopened"}).issue_commentability("https://github.com/example/project/issues/2")
        self.assertTrue(reopened["commentable"])

    def test_issue_link_note_search_is_exact_and_note_write_is_one_line(self) -> None:
        calls = []
        issue_url = "https://github.com/example/project/issues/2"
        pr_url = "https://github.com/example/project/pull/8"

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            if any(str(item).endswith("/comments") for item in argv) and "GET" in argv:
                pages = [[
                    {"id": 1, "body": "prefix " + pr_url},
                    {"id": 2, "body": pr_url},
                ]]
                return CompletedProcess(argv, 0, json.dumps(pages), "")
            return CompletedProcess(argv, 0, json.dumps({"id": 3, "html_url": "https://github.com/example/project/issues/comments/3"}), "")

        client = GhClient(fake_runner)
        matches = client.find_issue_link_note(issue_url, pr_url)
        self.assertEqual([item["id"] for item in matches], [2])
        client.add_issue_note(issue_url, pr_url)
        self.assertIn("body=" + pr_url, calls[-1])
        self.assertEqual(calls[-1][4], "POST")

    def test_pull_request_receipt_lifecycle_never_uses_issue_receipt_shape(self) -> None:
        packet = valid_packet()
        operation = build_operation(packet, "example/project", "pull_request", "Fix input", "Body", "main", "fix/input", packet["diff"])
        pr_url = "https://github.com/example/project/pull/7"
        with tempfile.TemporaryDirectory() as directory:
            path = operation_receipt_path(Path(directory) / ".reviewworthy" / "contribution.json", operation.operation_id)
            save_operation_pr_created(path, operation, pr_url)
            self.assertEqual(load_operation_receipt(path, operation)["status"], "pr_created")
            save_operation_link_attempted(path, operation, pr_url)
            self.assertEqual(load_operation_receipt(path, operation)["status"], "link_attempted")
            save_operation_needs_reconciliation(path, operation, pr_url, "issue_locked")
            self.assertEqual(load_operation_receipt(path, operation)["status"], "needs_reconciliation")
            save_operation_linked(path, operation, pr_url)
            linked = load_operation_receipt(path, operation)
            self.assertEqual(linked["status"], "linked")
            self.assertEqual(linked["pr_url"], pr_url)

    def test_operation_lock_rejects_concurrent_claim_and_releases_afterward(self) -> None:
        operation = build_operation(valid_packet(), "example/project", "issue", "Fix input", "Body")
        with tempfile.TemporaryDirectory() as directory:
            path = operation_receipt_path(Path(directory) / "packet.json", operation.operation_id)
            with operation_lock(path):
                with self.assertRaises(GhError):
                    with operation_lock(path):
                        pass
            with operation_lock(path):
                pass

    def test_find_existing_reads_all_pages_and_filters_issue_kind(self) -> None:
        packet = valid_packet()
        operation = build_operation(packet, "example/project", "issue", "Fix input", "Body")
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            if "page=1" in argv:
                page = [
                    {"number": number, "html_url": f"https://github.com/example/project/issues/{number}", "title": "Other", "body": "", "state": "open"}
                    for number in range(1, 101)
                ]
            else:
                page = [
                    {"number": 2, "html_url": "https://github.com/example/project/issues/2", "title": "Existing", "body": operation.marker, "state": "open"},
                    {"number": 3, "html_url": "https://github.com/example/project/pull/3", "title": "PR", "body": operation.marker, "state": "open", "pull_request": {}},
                ]
            return CompletedProcess(argv, 0, json.dumps(page), "")

        matches = GhClient(fake_runner).find_existing(operation)

        self.assertEqual([match["number"] for match in matches], [2])
        self.assertEqual(len(calls), 2)
        self.assertIn("page=1", calls[0])
        self.assertIn("page=2", calls[1])

    def test_multiple_current_marker_matches_require_reconciliation(self) -> None:
        operation = build_operation(valid_packet(), "example/project", "issue", "Fix input", "Body")

        def fake_runner(argv, **kwargs):
            records = [
                {"number": 2, "html_url": "https://github.com/example/project/issues/2", "body": operation.marker},
                {"number": 3, "html_url": "https://github.com/example/project/issues/3", "body": operation.marker},
            ]
            return CompletedProcess(argv, 0, json.dumps(records), "")

        with self.assertRaisesRegex(GhError, "Multiple remote records"):
            GhClient(fake_runner).find_existing(operation)

    def test_pull_request_head_reads_the_canonical_remote_commit(self) -> None:
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append(argv)
            return CompletedProcess(argv, 0, json.dumps({"head": {"sha": "a" * 40}}), "")

        head_sha = GhClient(fake_runner).pull_request_head("https://github.com/example/project/pull/8")

        self.assertEqual(head_sha, "a" * 40)
        self.assertEqual(
            calls[0],
            ["gh", "api", "repos/example/project/pulls/8", "--method", "GET"],
        )

    def test_pull_request_head_rejects_missing_remote_identity(self) -> None:
        def fake_runner(argv, **kwargs):
            return CompletedProcess(argv, 0, json.dumps({"head": {}}), "")

        with self.assertRaisesRegex(GhError, "head.sha"):
            GhClient(fake_runner).pull_request_head("https://github.com/example/project/pull/8")

    def test_operation_receipt_round_trip(self) -> None:
        operation = build_operation(valid_packet(), "example/project", "issue", "Fix input", "Body", "main")
        with tempfile.TemporaryDirectory() as directory:
            path = operation_receipt_path(Path(directory) / ".reviewworthy" / "contribution.json", operation.operation_id)
            save_operation_receipt(path, operation, "https://github.com/example/project/issues/7")
            receipt = load_operation_receipt(path, operation)
            self.assertEqual(receipt["remote"], "https://github.com/example/project/issues/7")
            self.assertEqual(receipt["state_version"], "0.3")
            self.assertIn("local/v0.3/operations", path.as_posix())

    def test_unversioned_operation_state_is_not_recognized(self) -> None:
        operation = build_operation(valid_packet(), "example/project", "issue", "Fix input", "Body")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps({
                "operation_id": operation.operation_id,
                "marker": operation.marker,
                "repo": operation.repo,
                "kind": operation.kind,
                "operation": operation.as_dict(),
                "status": "succeeded",
                "remote": "https://github.com/example/project/issues/7",
                "recorded_at": "2026-08-09T00:00:00Z",
            }), encoding="utf-8")

            with self.assertRaisesRegex(GhError, "does not match"):
                load_operation_receipt(path, operation)

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
