from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from reviewworthy.cli import _issue_revalidation_errors, main
from reviewworthy.evidence import append_evidence_summary, build_evidence_summary
from reviewworthy.git import capture_pr_diff, verification_plan_digest
from reviewworthy.github import GhError
from reviewworthy.packet import semantic_snapshot, readiness_blockers, skeleton_packet, validate_packet
from reviewworthy.signal import skeleton_signal, validate_signal

from helpers import valid_packet


class CliBoundaryTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        return completed.stdout.strip()

    def _pr_repository(self, root: Path) -> tuple[Path, dict[str, object]]:
        repository_root = root / "git-repository"
        repository_root.mkdir()
        self._git(repository_root, "init", "-q")
        self._git(repository_root, "config", "user.email", "test@example.invalid")
        self._git(repository_root, "config", "user.name", "Reviewworthy Test")
        self._git(repository_root, "branch", "-M", "main")
        (repository_root / "src").mkdir()
        (repository_root / "src" / "example.py").write_text("one\n", encoding="utf-8")
        self._git(repository_root, "add", "src/example.py")
        self._git(repository_root, "commit", "-qm", "base")
        self._git(repository_root, "checkout", "-qb", "feature")
        (repository_root / "src" / "example.py").write_text("one\ntwo\n", encoding="utf-8")
        self._git(repository_root, "commit", "-qam", "feature")
        self._git(repository_root, "checkout", "-q", "main")
        (repository_root / "only-main.txt").write_text("base-only\n", encoding="utf-8")
        self._git(repository_root, "add", "only-main.txt")
        self._git(repository_root, "commit", "-qm", "advance base")
        self._git(repository_root, "checkout", "-q", "feature")
        return repository_root, capture_pr_diff(repository_root, "main", "feature")

    def test_signal_init_and_require_confirmed_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            signal_path = Path(directory) / "signal.json"
            with redirect_stdout(io.StringIO()):
                init_code = main(
                    [
                        "signal",
                        "init",
                        "--record-type",
                        "issue",
                        "--claim-type",
                        "maintainer_request",
                        "--reference",
                        "https://github.com/example/project/issues/2",
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
                "signal_version": "0.3",
                "record_type": "issue",
                "claim_type": "maintainer_request",
                "reference": "",
                "lifecycle": "pending",
                "evidence": [],
                "authority": {"kind": "contributor", "actor": "", "asserted_at": ""},
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
                    "signal", "publish", "create", str(published_path), "--repo", "Example/Project",
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
            self.assertIn("publication", published)
            self.assertNotIn("published", published)
            self.assertEqual(published["reference"], "https://github.com/example/project/issues/9")
            self.assertEqual(fake_client.create.call_count, 1)

    def test_signal_verify_checks_github_reference_without_mutating_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            signal_path = Path(directory) / "signal.json"
            signal = {
                "signal_version": "0.3",
                "record_type": "issue",
                "claim_type": "bug_report",
                "reference": "https://github.com/example/project/issues/2",
                "lifecycle": "pending",
                "evidence": [],
                "authority": {"kind": "contributor", "actor": "", "asserted_at": ""},
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

    def test_issue_revalidation_normalizes_state_reason_and_duplicate_label(self) -> None:
        packet = valid_packet()
        base_remote = {
            "verified": True,
            "host": "github.com",
            "record_type": "issue",
            "repository": "Example/Project",
            "repository_id": 101,
            "number": 1,
            "url": "https://github.com/example/project/issues/1",
            "visibility": "public",
            "labels": [],
        }
        for state_reason in ("not_planned", "not-planned", "not planned"):
            errors = _issue_revalidation_errors(packet, {**base_remote, "state_reason": state_reason})
            self.assertIn("issue_not_actionable", {error["code"] for error in errors})
        for state_reason in ("completed", "reopened"):
            errors = _issue_revalidation_errors(packet, {**base_remote, "state_reason": state_reason})
            self.assertNotIn("issue_not_actionable", {error["code"] for error in errors})
        errors = _issue_revalidation_errors(packet, {**base_remote, "state_reason": "duplicate"})
        self.assertNotIn("issue_not_actionable", {error["code"] for error in errors})
        errors = _issue_revalidation_errors(packet, {**base_remote, "labels": ["Duplicate"]})
        self.assertIn("issue_duplicate", {error["code"] for error in errors})

    def test_issue_revalidation_applies_good_first_policy_to_live_labels(self) -> None:
        packet = valid_packet()
        packet["policy"]["authoritative_claims"]["good_first_issue_ai_allowed"] = False
        packet["basis"]["labels"] = ["good first issue"]
        base_remote = {
            "verified": True,
            "host": "github.com",
            "record_type": "issue",
            "repository": "example/project",
            "repository_id": 101,
            "number": 1,
            "url": "https://github.com/example/project/issues/1",
            "visibility": "public",
            "labels": [],
        }

        self.assertNotIn("good_first_issue_ai_disallowed", {error["code"] for error in _issue_revalidation_errors(packet, base_remote)})
        self.assertIn("good_first_issue_label_verification_required", {error["code"] for error in _issue_revalidation_errors(packet, {key: value for key, value in base_remote.items() if key != "labels"})})
        self.assertIn("issue_revalidation_repository_mismatch", {error["code"] for error in _issue_revalidation_errors(packet, {**base_remote, "number": True})})
        self.assertIn("issue_revalidation_identity_mismatch", {error["code"] for error in _issue_revalidation_errors(packet, {**base_remote, "repository_id": True})})
        errors = _issue_revalidation_errors(packet, {**base_remote, "labels": ["Good-First-Issue"]})

        self.assertIn("good_first_issue_ai_disallowed", {error["code"] for error in errors})

    def test_signal_verify_can_explicitly_record_successful_public_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            signal_path = Path(directory) / "signal.json"
            signal = {
                "signal_version": "0.3",
                "record_type": "issue",
                "claim_type": "bug_report",
                "reference": "https://github.com/example/project/issues/2",
                "lifecycle": "pending",
                "evidence": [],
                "authority": {"kind": "contributor", "actor": "", "asserted_at": ""},
            }
            signal_path.write_text(json.dumps(signal), encoding="utf-8")
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {
                "verified": True,
                "provider": "github",
                "host": "github.com",
                "repository": "example/project",
                "repository_id": 101,
                "record_type": "issue",
                "number": 2,
                "url": signal["reference"],
                "visibility": "public",
                "labels": ["Good First Issue"],
            }
            with patch("reviewworthy.cli.GhClient", return_value=fake_client), redirect_stdout(io.StringIO()):
                code = main(["signal", "verify", str(signal_path), "--record", "--json"])

            recorded = json.loads(signal_path.read_text())
            self.assertEqual(code, 0)
            self.assertEqual(recorded["verification"]["status"], "verified")
            self.assertEqual(recorded["verification"]["reference"], signal["reference"])
            self.assertEqual(recorded["verification"]["host"], "github.com")
            self.assertEqual(recorded["verification"]["repository_id"], 101)
            self.assertEqual(recorded["verification"]["labels"], ["Good First Issue"])

            packet = valid_packet()
            packet["policy"]["authoritative_claims"]["good_first_issue_ai_allowed"] = False
            packet["basis"] = {"kind": "signal", "signal": recorded}
            self.assertIn("good_first_issue_ai_disallowed", {item["code"] for item in readiness_blockers(packet)})

    def test_discussion_signal_verify_reaches_graphql_adapter_and_records_current_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            signal_path = Path(directory) / "signal.json"
            reference = "https://github.com/example/project/discussions/4"
            signal = skeleton_signal("discussion", "accepted_proposal", reference)
            signal_path.write_text(json.dumps(signal), encoding="utf-8")
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {
                "verified": True,
                "provider": "github",
                "host": "github.com",
                "repository": "example/project",
                "repository_id": 101,
                "record_type": "discussion",
                "number": 4,
                "url": reference,
                "visibility": "public",
                "state": "open",
            }

            with patch("reviewworthy.cli.GhClient", return_value=fake_client), redirect_stdout(io.StringIO()):
                code = main(["signal", "verify", str(signal_path), "--record", "--json"])

            recorded = json.loads(signal_path.read_text())
            self.assertEqual(code, 0)
            fake_client.verify_public_reference.assert_called_once_with(reference)
            self.assertEqual(recorded["verification"]["record_type"], "discussion")
            self.assertTrue(validate_signal(recorded)["valid"])

    def test_issue_verify_records_into_current_signal_backed_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet = valid_packet()
            reference = "https://github.com/example/project/issues/2"
            packet["basis"] = {
                "kind": "signal",
                "references": [reference],
                "evidence": [],
                "signal": skeleton_signal("issue", "bug_report", reference),
            }
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {
                "verified": True,
                "provider": "github",
                "host": "github.com",
                "reference": reference,
                "repository": "example/project",
                "repository_id": 101,
                "record_type": "issue",
                "number": 2,
                "url": reference,
                "visibility": "public",
                "state": "open",
                "labels": [],
            }

            with patch("reviewworthy.cli.GhClient", return_value=fake_client), redirect_stdout(io.StringIO()):
                code = main(["issue", "verify", "--packet", str(packet_path), "--record", "--json"])

            recorded = json.loads(packet_path.read_text())
            self.assertEqual(code, 0)
            self.assertEqual(recorded["basis"]["signal"]["verification"]["record_type"], "issue")

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
                    "duplicate_search": {"checked": True, "matches": [], "disposition": "not_duplicate"},
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
                    "--topic", "verification", "--topic", "policy",
                    "--rubric", "behavior=The changed behavior is bounded.",
                    "--rubric", "invariant=The existing invariant remains.",
                    "--rubric", "test=The focused test covers the path.", "--json",
                ])
                assessment_code = main([
                    "understanding", "record", str(packet_path), "--phase", "assessment", "--status", "passed",
                    "--question", "What changed?", "--answer", "The selected boundary changed.",
                    "--rubric", "behavior=The changed behavior is bounded.",
                    "--rubric", "invariant=The existing invariant remains.",
                    "--rubric", "test=The focused test covers the path.", "--json",
                ])
                validate_code = main(["understanding", "validate", str(packet_path), "--json"])

            bound = json.loads(packet_path.read_text())
            self.assertEqual(select_code, 0)
            self.assertEqual(bind_code, 0)
            self.assertEqual(orientation_code, 0)
            self.assertEqual(assessment_code, 0)
            self.assertEqual(validate_code, 0)
            self.assertEqual(bound["candidate_selection"]["candidate_id"], "candidate-001")

    def test_packet_init_rejects_path_traversal_contribution_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with redirect_stdout(io.StringIO()):
                code = main(["packet", "init", "--contribution-id", "../../escaped", "--root", str(root), "--mode", "issue-backed", "--json"])

            self.assertEqual(code, 2)
            self.assertFalse((root / "escaped" / "packet.json").exists())

    def test_candidate_transition_command_records_human_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet = valid_packet()
            packet["candidate_selection"] = {
                "candidate_id": "candidate-transition",
                "repository": "example/project",
                "menu_snapshot": "menu-sha",
                "recommendation": "issue_only",
                "duplicate_disposition": "not_duplicate",
                "confirmed": True,
            }
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                code = main([
                    "candidate", "transition", "--packet", str(packet_path), "--to", "plan_directly",
                    "--reason", "A valid public Issue now exists.", "--confirm", "--json",
                ])

            updated = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(updated["candidate_selection"]["transition"]["to"], "plan_directly")
            self.assertTrue(updated["candidate_selection"]["transition"]["human_confirmed"])

    def test_candidate_transition_command_rejects_incomplete_current_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet = valid_packet()
            packet["candidate_selection"] = {
                "candidate_id": "candidate-old",
                "repository": "example/project",
                "menu_snapshot": "menu-sha",
                "duplicate_disposition": "not_duplicate",
                "confirmed": True,
            }
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                code = main([
                    "candidate", "transition", "--packet", str(packet_path),
                    "--to", "plan_directly",
                    "--reason", "The verified Issue now bounds the change.", "--confirm", "--json",
                ])

            unchanged = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertNotIn("transition", unchanged["candidate_selection"])

    def test_action_cli_recomputes_pr_diff_from_public_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root, actual_diff = self._pr_repository(root)
            packet = valid_packet()
            packet["diff"] = dict(actual_diff)
            body = append_evidence_summary("Body", build_evidence_summary(packet, actual_diff))
            event_path = root / "event.json"
            event_path.write_text(json.dumps({
                "repository": {"full_name": "example/project", "id": 101},
                "pull_request": {
                    "base": {"sha": actual_diff["base_tip_sha"]},
                    "head": {"sha": actual_diff["head_sha"]},
                    "body": body,
                }
            }), encoding="utf-8")
            output = io.StringIO()

            with patch.dict(os.environ, {
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event_path),
            }, clear=False), redirect_stdout(output):
                code = main([
                    "action", "check", "--root", str(repository_root),
                    "--mode", "evidence-enforce", "--json",
                ])

            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result["violations"], [])

    def test_packet_init_defaults_to_ignored_local_contribution_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main([
                    "packet", "init", "--root", str(root),
                    "--contribution-id", "local-001", "--json",
                ])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            created = Path(result["created"])
            self.assertTrue(created.is_file())
            self.assertIn(".git/reviewworthy/v0.3/contributions/local-001/packet.json", str(created))
            self.assertEqual(self._git(root, "status", "--porcelain=v1", "--untracked-files=all"), "")

    def test_verify_cli_persists_invalid_receipt_and_returns_failure_when_head_moves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root, actual_diff = self._pr_repository(root)
            expected_head = self._git(repository_root, "rev-parse", "HEAD")
            packet_path = root / "packet.json"
            command = (
                "from pathlib import Path; import subprocess; "
                "Path('src/example.py').write_text('one\\ntwo\\nthree\\n'); "
                "subprocess.run(['git', 'add', 'src/example.py'], check=True); "
                "subprocess.run(['git', 'commit', '-qm', 'verification mutation'], check=True)"
            )
            output = io.StringIO()
            packet = valid_packet()
            packet["diff"] = actual_diff
            packet["verification"]["plan"]["checks"][0]["argv"] = [sys.executable, "-c", command]
            packet["verification"]["plan_digest"] = verification_plan_digest(packet["verification"]["plan"])
            packet["verification"]["receipts"] = []
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")

            with redirect_stdout(output):
                code = main([
                    "verify", "run", "--root", str(repository_root), "--packet", str(packet_path),
                    "--check-id", "unit", "--json",
                ])

            result = json.loads(output.getvalue())
            persisted = json.loads(packet_path.read_text(encoding="utf-8"))["verification"]["receipts"][0]
            self.assertEqual(code, 1)
            self.assertEqual(result["integrity_status"], "invalid")
            self.assertEqual(result["failure_reason"], "head_changed_after_execution")
            self.assertEqual(persisted["check_id"], "unit")
            self.assertEqual(persisted["integrity_status"], "invalid")

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
                        "--base",
                        "HEAD",
                        "--head",
                        "HEAD",
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
                        "--base",
                        "HEAD",
                        "--head",
                        "HEAD",
                        "--json",
                    ]
                )
            self.assertEqual(mismatch_code, 2)

    def test_remote_plan_rejects_packet_when_recomputed_diff_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root, actual_diff = self._pr_repository(root)
            packet = valid_packet()
            packet["repository"]["base_sha"] = actual_diff["base_tip_sha"]
            packet["diff"] = dict(actual_diff)
            packet["verification"]["receipts"][0].update({
                "subject_digest": actual_diff["subject_digest"],
                "head_sha": actual_diff["head_sha"],
                "head_sha_before": actual_diff["head_sha"],
                "head_sha_after": actual_diff["head_sha"],
                "cwd": ".",
            })
            packet["diff"]["additions"] = actual_diff["additions"] + 1
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet_path = root / "packet.json"
            body_path = root / "body.md"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            body_path.write_text(packet["narrative"]["body"], encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                code = main([
                    "remote", "plan", "--packet", str(packet_path), "--repo", "example/project",
                    "--kind", "pull_request", "--title", packet["narrative"]["title"],
                    "--body-file", str(body_path), "--base", "main", "--head", "feature",
                    "--root", str(repository_root), "--json",
                ])

            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertIn("remote_additions_mismatch", {item["code"] for item in result["readiness_blockers"]})

    def test_remote_plan_compares_every_recomputed_diff_field(self) -> None:
        fields = {
            "comparison": "two_tip",
            "base_tip_sha": "0" * 40,
            "merge_base_sha": "2" * 40,
            "head_sha": "1" * 40,
            "subject_digest": "0" * 64,
            "fingerprint_algorithm": "other-algorithm",
            "changed_files": ["src/other.py"],
            "additions": 1,
            "deletions": 1,
        }
        blocker_codes = {
            field: f"remote_{field}_mismatch" for field in fields
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root, actual_diff = self._pr_repository(root)
            for field, value in fields.items():
                packet = valid_packet()
                packet["repository"]["base_sha"] = actual_diff["base_tip_sha"]
                packet["diff"] = dict(actual_diff)
                packet["diff"][field] = actual_diff[field] + 1 if field in {"additions", "deletions"} else value
                packet["verification"]["receipts"][0].update({
                    "subject_digest": actual_diff["subject_digest"],
                    "head_sha": actual_diff["head_sha"],
                    "head_sha_before": actual_diff["head_sha"],
                    "head_sha_after": actual_diff["head_sha"],
                    "cwd": ".",
                })
                packet["snapshots"]["semantic"] = semantic_snapshot(packet)
                packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
                packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
                packet_path = root / "packet.json"
                body_path = root / "body.md"
                packet_path.write_text(json.dumps(packet), encoding="utf-8")
                body_path.write_text(packet["narrative"]["body"], encoding="utf-8")

                output = io.StringIO()
                with redirect_stdout(output):
                    code = main([
                        "remote", "plan", "--packet", str(packet_path), "--repo", "example/project",
                        "--kind", "pull_request", "--title", packet["narrative"]["title"],
                        "--body-file", str(body_path), "--base", "main", "--head", "feature",
                        "--root", str(repository_root), "--json",
                    ])

                result = json.loads(output.getvalue())
                self.assertEqual(code, 0, field)
                self.assertIn(blocker_codes[field], {item["code"] for item in result["readiness_blockers"]})

    def test_remote_create_rejects_every_recomputed_diff_mismatch_before_create(self) -> None:
        fields = {
            "comparison": "two_tip",
            "base_tip_sha": "0" * 40,
            "merge_base_sha": "2" * 40,
            "head_sha": "1" * 40,
            "subject_digest": "0" * 64,
            "fingerprint_algorithm": "other-algorithm",
            "changed_files": ["src/other.py"],
            "additions": 1,
            "deletions": 1,
        }
        blocker_codes = {
            field: f"remote_{field}_mismatch" for field in fields
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root, actual_diff = self._pr_repository(root)
            for field, value in fields.items():
                packet = valid_packet()
                packet["repository"]["base_sha"] = actual_diff["base_tip_sha"]
                packet["diff"] = dict(actual_diff)
                packet["diff"][field] = actual_diff[field] + 1 if field in {"additions", "deletions"} else value
                packet["verification"]["receipts"][0].update({
                    "subject_digest": actual_diff["subject_digest"],
                    "head_sha": actual_diff["head_sha"],
                    "head_sha_before": actual_diff["head_sha"],
                    "head_sha_after": actual_diff["head_sha"],
                    "cwd": ".",
                })
                packet["snapshots"]["semantic"] = semantic_snapshot(packet)
                packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
                packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
                packet_path = root / "packet.json"
                body_path = root / "body.md"
                packet_path.write_text(json.dumps(packet), encoding="utf-8")
                body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
                plan_output = io.StringIO()
                plan_args = [
                    "remote", "plan", "--packet", str(packet_path), "--repo", "example/project",
                    "--kind", "pull_request", "--title", packet["narrative"]["title"],
                    "--body-file", str(body_path), "--base", "main", "--head", "feature",
                    "--root", str(repository_root), "--json",
                ]
                with redirect_stdout(plan_output):
                    self.assertEqual(main(plan_args), 0, field)
                operation_id = json.loads(plan_output.getvalue())["operation_id"]

                create_output = io.StringIO()
                create_args = list(plan_args)
                create_args[1] = "create"
                create_args = [*create_args[:-1], "--confirm-operation-id", operation_id, "--json"]
                with patch("reviewworthy.cli.GhClient") as client_class, redirect_stdout(create_output):
                    code = main(create_args)

                result = json.loads(create_output.getvalue())
                self.assertEqual(code, 1, field)
                self.assertIn(blocker_codes[field], {item["code"] for item in result["readiness_blockers"]})
                client_class.return_value.create.assert_not_called()

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
            repository_root, actual_diff = self._pr_repository(root)
            packet = valid_packet()
            packet["repository"]["base_sha"] = actual_diff["base_tip_sha"]
            packet["diff"] = actual_diff
            packet["verification"]["receipts"][0].update({
                "subject_digest": actual_diff["subject_digest"],
                "head_sha": actual_diff["head_sha"],
                "head_sha_before": actual_diff["head_sha"],
                "head_sha_after": actual_diff["head_sha"],
                "cwd": ".",
            })
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
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
                "--head", "feature",
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
                "host": "github.com",
                "repository": "example/project",
                "repository_id": 101,
                "record_type": "issue",
                "number": 1,
                "url": "https://github.com/example/project/issues/1",
                "visibility": "public",
                "labels": [],
                "state": "open",
            }
            fake_client.find_existing.return_value = []
            fake_client.create.return_value = "https://github.com/example/project/pull/8"
            fake_client.pull_request_head.return_value = actual_diff["head_sha"]
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
            self.assertEqual(fake_client.pull_request_head.call_count, 2)
            self.assertEqual(fake_client.add_issue_note.call_count, 1)

    def test_pull_request_remote_head_uncertainty_requires_reconciliation_before_linking(self) -> None:
        cases = (
            ("created_mismatch", False, "mismatch", "remote_pr_head_mismatch"),
            ("created_unavailable", False, "unavailable", "remote_pr_head_unavailable"),
            ("existing_mismatch", True, "mismatch", "remote_pr_head_mismatch"),
            ("head_moves_before_note", False, "moves", "remote_pr_head_mismatch"),
        )
        for name, use_existing, remote_mode, expected_reason in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repository_root, actual_diff = self._pr_repository(root)
                packet = valid_packet()
                packet["repository"]["base_sha"] = actual_diff["base_tip_sha"]
                packet["diff"] = actual_diff
                packet["verification"]["receipts"][0].update({
                    "subject_digest": actual_diff["subject_digest"],
                    "head_sha": actual_diff["head_sha"],
                    "head_sha_before": actual_diff["head_sha"],
                    "head_sha_after": actual_diff["head_sha"],
                    "cwd": ".",
                })
                packet["snapshots"]["semantic"] = semantic_snapshot(packet)
                packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
                packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
                packet_path = root / "packet.json"
                body_path = root / "body.md"
                packet_path.write_text(json.dumps(packet), encoding="utf-8")
                body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
                common = [
                    "--packet", str(packet_path), "--repo", "example/project", "--kind", "pull_request",
                    "--title", packet["narrative"]["title"], "--body-file", str(body_path), "--base", "main",
                    "--head", "feature", "--root", str(repository_root),
                ]
                plan_output = io.StringIO()
                with redirect_stdout(plan_output):
                    self.assertEqual(main(["remote", "plan", *common, "--json"]), 0)
                operation_id = json.loads(plan_output.getvalue())["operation_id"]
                fake_client = unittest.mock.MagicMock()
                fake_client.verify_public_reference.return_value = {
                    "verified": True,
                    "provider": "github",
                    "host": "github.com",
                    "repository": "example/project",
                    "repository_id": 101,
                    "record_type": "issue",
                    "number": 1,
                    "url": "https://github.com/example/project/issues/1",
                    "visibility": "public",
                    "labels": [],
                }
                fake_client.find_existing.return_value = (
                    [{"url": "https://github.com/example/project/pull/10"}]
                    if use_existing
                    else []
                )
                fake_client.create.return_value = "https://github.com/example/project/pull/10"
                fake_client.find_issue_link_note.return_value = []
                fake_client.issue_commentability.return_value = {"commentable": True}
                if remote_mode == "unavailable":
                    fake_client.pull_request_head.side_effect = GhError("head unavailable")
                elif remote_mode == "moves":
                    fake_client.pull_request_head.side_effect = [actual_diff["head_sha"], "f" * 40]
                else:
                    fake_client.pull_request_head.return_value = "f" * 40
                create_args = ["remote", "create", *common, "--confirm-operation-id", operation_id, "--json"]
                first_output = io.StringIO()
                second_output = io.StringIO()
                with patch("reviewworthy.cli.GhClient", return_value=fake_client):
                    with redirect_stdout(first_output):
                        first_code = main(create_args)
                    with redirect_stdout(second_output):
                        second_code = main(create_args)

                result = json.loads(first_output.getvalue())
                receipt_files = list((root / "local" / "operations").glob("*.json"))
                self.assertEqual((first_code, second_code), (1, 1))
                self.assertEqual(result["outcome"], "needs_reconciliation")
                self.assertTrue(result["reason"].startswith(expected_reason))
                self.assertEqual(json.loads(receipt_files[0].read_text())["status"], "needs_reconciliation")
                self.assertEqual(fake_client.create.call_count, 0 if use_existing else 1)
                self.assertEqual(fake_client.pull_request_head.call_count, 2 if remote_mode == "moves" else 1)
                if remote_mode == "moves":
                    self.assertEqual(fake_client.find_issue_link_note.call_count, 1)
                    self.assertEqual(fake_client.issue_commentability.call_count, 1)
                else:
                    fake_client.find_issue_link_note.assert_not_called()
                    fake_client.issue_commentability.assert_not_called()
                fake_client.add_issue_note.assert_not_called()

    def test_pull_request_create_checks_live_good_first_label_before_remote_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root, actual_diff = self._pr_repository(root)
            packet = valid_packet()
            packet["repository"]["base_sha"] = actual_diff["base_tip_sha"]
            packet["diff"] = actual_diff
            packet["verification"]["receipts"][0].update({
                "subject_digest": actual_diff["subject_digest"],
                "head_sha": actual_diff["head_sha"],
                "head_sha_before": actual_diff["head_sha"],
                "head_sha_after": actual_diff["head_sha"],
                "cwd": ".",
            })
            packet["policy"]["authoritative_claims"]["good_first_issue_ai_allowed"] = False
            packet["basis"]["verification"]["labels"] = []
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet_path = root / "packet.json"
            body_path = root / "body.md"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
            common = [
                "--packet", str(packet_path), "--repo", "example/project", "--kind", "pull_request",
                "--title", packet["narrative"]["title"], "--body-file", str(body_path), "--base", "main",
                "--head", "feature", "--root", str(repository_root),
            ]
            plan_output = io.StringIO()
            with redirect_stdout(plan_output):
                self.assertEqual(main(["remote", "plan", *common, "--json"]), 0)
            operation_id = json.loads(plan_output.getvalue())["operation_id"]
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {
                "verified": True,
                "host": "github.com",
                "repository": "example/project",
                "repository_id": 101,
                "record_type": "issue",
                "number": 1,
                "url": "https://github.com/example/project/issues/1",
                "visibility": "public",
                "labels": ["Good First Issue"],
            }
            output = io.StringIO()

            with patch("reviewworthy.cli.GhClient", return_value=fake_client), redirect_stdout(output):
                code = main(["remote", "create", *common, "--confirm-operation-id", operation_id, "--json"])

            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertIn("good_first_issue_ai_disallowed", {item["code"] for item in result["readiness_blockers"]})
            fake_client.find_existing.assert_not_called()
            fake_client.create.assert_not_called()
            fake_client.add_issue_note.assert_not_called()

    def test_pull_request_link_failure_is_terminal_without_creating_another_pr(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root, actual_diff = self._pr_repository(root)
            packet = valid_packet()
            packet["repository"]["base_sha"] = actual_diff["base_tip_sha"]
            packet["diff"] = actual_diff
            packet["verification"]["receipts"][0].update({
                "subject_digest": actual_diff["subject_digest"],
                "head_sha": actual_diff["head_sha"],
                "head_sha_before": actual_diff["head_sha"],
                "head_sha_after": actual_diff["head_sha"],
                "cwd": ".",
            })
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet_path = root / "packet.json"
            body_path = root / "body.md"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            body_path.write_text(packet["narrative"]["body"], encoding="utf-8")
            common = [
                "--packet", str(packet_path), "--repo", "example/project", "--kind", "pull_request",
                "--title", packet["narrative"]["title"], "--body-file", str(body_path), "--base", "main",
                "--head", "feature", "--root", str(repository_root),
            ]
            plan_output = io.StringIO()
            with redirect_stdout(plan_output):
                main(["remote", "plan", *common, "--json"])
            operation_id = json.loads(plan_output.getvalue())["operation_id"]
            fake_client = unittest.mock.MagicMock()
            fake_client.verify_public_reference.return_value = {
                "verified": True,
                "host": "github.com",
                "repository": "example/project",
                "repository_id": 101,
                "record_type": "issue",
                "number": 1,
                "url": "https://github.com/example/project/issues/1",
                "visibility": "public",
                "labels": [],
            }
            fake_client.find_existing.return_value = []
            fake_client.create.return_value = "https://github.com/example/project/pull/9"
            fake_client.pull_request_head.return_value = actual_diff["head_sha"]
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
