from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from reviewworthy.action import check_packet, github_event_context
from reviewworthy.contract import contract_snapshot
from reviewworthy.git import PR_DIFF_FIELDS, capture_pr_diff
from reviewworthy.packet import material_snapshot

from helpers import valid_packet


class ActionCheckTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        return completed.stdout.strip()

    def test_composite_action_is_read_only_and_uses_action_check(self) -> None:
        action_path = Path(__file__).parents[1] / "action.yml"
        content = action_path.read_text(encoding="utf-8")

        self.assertIn("using: composite", content)
        self.assertIn("python -m reviewworthy action check", content)
        self.assertIn("fetch-depth: 0", (Path(__file__).parents[1] / ".github/workflows/reviewworthy.yml").read_text(encoding="utf-8"))
        self.assertIn("capture_pr_diff(", (Path(__file__).parents[1] / "src/reviewworthy/action.py").read_text(encoding="utf-8"))
        self.assertIn("GITHUB_EVENT_PATH", (Path(__file__).parents[1] / "src/reviewworthy/action.py").read_text(encoding="utf-8"))
        self.assertIn("pull_request", content)
        self.assertIn("--root .", content)
        self.assertIn("REVIEWWORTHY_MODE", content)
        self.assertIn("--changed-files-provided", content)
        self.assertIn("--changed-files-unavailable", content)
        self.assertIn("mode:", content)
        self.assertIn("require-packet:", content)
        self.assertIn("fail-on-unknown:", content)
        self.assertIn("require-current-diff:", content)
        self.assertIn("mode must be report or enforce", content)
        self.assertNotIn("gh pr create", content)
        self.assertNotIn("gh issue create", content)
        self.assertNotIn("git fetch", content)

    def test_action_reads_pull_request_identity_from_runner_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "event.json"
            event_path.write_text(json.dumps({
                "pull_request": {
                    "base": {"sha": "base-from-event"},
                    "head": {"sha": "head-from-event"},
                }
            }), encoding="utf-8")

            with patch.dict(os.environ, {
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event_path),
            }, clear=False):
                self.assertEqual(
                    github_event_context(),
                    ("pull_request", "base-from-event", "head-from-event"),
                )

    def test_composite_enforce_script_runs_against_real_pull_request_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository_root = root / "repository"
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
            actual_diff = capture_pr_diff(repository_root, "main", "feature")
            self.assertEqual(actual_diff["changed_files"], ["src/example.py"])

            packet = valid_packet()
            packet["repository"]["base_sha"] = actual_diff["base_tip_sha"]
            packet["diff"] = dict(actual_diff)
            packet["verification"]["receipts"][0].update({
                "head_sha": actual_diff["head_sha"],
                "head_sha_before": actual_diff["head_sha"],
                "head_sha_after": actual_diff["head_sha"],
                "cwd": ".",
            })
            packet["policy"]["authoritative_claims"] = {
                "ai_assistance": "allowed",
                "issue_required": False,
                "disclosure_required": False,
                "disclosure_locations": [],
                "disclosure_stages": [],
                "human_pr_narrative_required": False,
                "security_private_reporting": False,
                "draft_pr_required": False,
                "discovery_evidence_allowed": True,
                "good_first_issue_ai_allowed": True,
            }
            snapshot = material_snapshot(packet)
            packet["materials"]["material_snapshot"] = snapshot
            packet["understanding"]["orientation"]["material_snapshot"] = snapshot
            packet["understanding"]["assessment"]["material_snapshot"] = snapshot
            packet_path = repository_root / "packet.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            event_path = root / "event.json"
            event_path.write_text(json.dumps({
                "pull_request": {
                    "base": {"sha": actual_diff["base_tip_sha"]},
                    "head": {"sha": actual_diff["head_sha"]},
                }
            }), encoding="utf-8")

            action_path = Path(__file__).parents[1] / "action.yml"
            script = textwrap.dedent(action_path.read_text(encoding="utf-8").split("      run: |\n", 1)[1])
            environment = os.environ.copy()
            environment.update({
                "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
                "REVIEWWORTHY_PACKET": "packet.json",
                "REVIEWWORTHY_CHANGED_FILES": "src/forged.py",
                "REVIEWWORTHY_MODE": "enforce",
                "REVIEWWORTHY_REQUIRE_PACKET": "false",
                "REVIEWWORTHY_FAIL_ON_UNKNOWN": "false",
                "REVIEWWORTHY_REQUIRE_CURRENT_DIFF": "false",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event_path),
            })
            completed = subprocess.run(
                ["bash", "-c", script],
                cwd=repository_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["conclusion"], "success")
            self.assertEqual(result["violations"], [])

    def test_missing_packet_is_unknown_but_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = check_packet(Path(directory) / "missing.json")
            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(result["unknowns"])

    def test_enforce_mode_requires_packet_and_current_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = check_packet(Path(directory) / "missing.json", mode="enforce")
            self.assertEqual(missing["conclusion"], "failure")
            self.assertIn("packet_required", {violation["code"] for violation in missing["violations"]})
            self.assertEqual(missing["requirements"], {
                "require_packet": True,
                "fail_on_unknown": True,
                "require_current_diff": True,
            })

            packet_path = Path(directory) / "packet.json"
            packet_path.write_text(json.dumps(valid_packet()), encoding="utf-8")
            enforced = check_packet(packet_path, mode="enforce")
            self.assertEqual(enforced["conclusion"], "failure")
            self.assertIn("current_diff_required", {violation["code"] for violation in enforced["violations"]})

    def test_enforce_mode_can_pass_with_complete_policy_and_current_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"]["authoritative_claims"] = {
                "ai_assistance": "allowed",
                "issue_required": False,
                "disclosure_required": False,
                "disclosure_locations": [],
                "disclosure_stages": [],
                "human_pr_narrative_required": False,
                "security_private_reporting": False,
                "draft_pr_required": False,
                "discovery_evidence_allowed": True,
                "good_first_issue_ai_allowed": True,
            }
            snapshot = material_snapshot(packet)
            packet["materials"]["material_snapshot"] = snapshot
            packet["understanding"]["orientation"]["material_snapshot"] = snapshot
            packet["understanding"]["assessment"]["material_snapshot"] = snapshot
            packet_path = Path(directory) / "packet.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")

            current_diff = {key: packet["diff"][key] for key in PR_DIFF_FIELDS}
            with patch("reviewworthy.action.capture_pr_diff", return_value=current_diff) as capture:
                result = check_packet(
                    packet_path,
                    current_diff["changed_files"],
                    root=Path(directory),
                    current_diff=current_diff,
                    current_diff_available=True,
                    event_name="pull_request",
                    event_base_sha="base-sha",
                    event_head_sha="head-sha",
                    mode="enforce",
                )

            self.assertEqual(result["conclusion"], "success")
            self.assertEqual(result["violations"], [])
            self.assertEqual(result["unknowns"], [])
            capture.assert_called_once_with(Path(directory), "base-sha", "head-sha")

    def test_enforce_mode_requires_real_pull_request_context_and_receipt_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"]["authoritative_claims"] = {
                "ai_assistance": "allowed",
                "issue_required": False,
                "disclosure_required": False,
                "disclosure_locations": [],
                "disclosure_stages": [],
                "human_pr_narrative_required": False,
                "security_private_reporting": False,
                "draft_pr_required": False,
                "discovery_evidence_allowed": True,
                "good_first_issue_ai_allowed": True,
            }
            snapshot = material_snapshot(packet)
            packet["materials"]["material_snapshot"] = snapshot
            packet["understanding"]["orientation"]["material_snapshot"] = snapshot
            packet["understanding"]["assessment"]["material_snapshot"] = snapshot
            packet_path = Path(directory) / "packet.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            current_diff = {key: packet["diff"][key] for key in PR_DIFF_FIELDS}

            context_result = check_packet(
                packet_path,
                current_diff=current_diff,
                event_name="push",
                event_base_sha="base-sha",
                event_head_sha="new-head-sha",
                mode="enforce",
            )

            context_codes = {violation["code"] for violation in context_result["violations"]}
            self.assertIn("pull_request_context_required", context_codes)

            with patch("reviewworthy.action.capture_pr_diff", return_value=current_diff):
                binding_result = check_packet(
                    packet_path,
                    current_diff=current_diff,
                    root=Path(directory),
                    event_name="pull_request",
                    event_base_sha="base-sha",
                    event_head_sha="new-head-sha",
                    mode="enforce",
                )

            binding_codes = {violation["code"] for violation in binding_result["violations"]}
            self.assertIn("verification_head_mismatch", binding_codes)

    def test_enforce_mode_compares_complete_current_diff_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"]["authoritative_claims"] = {
                "ai_assistance": "allowed",
                "issue_required": False,
                "disclosure_required": False,
                "disclosure_locations": [],
                "disclosure_stages": [],
                "human_pr_narrative_required": False,
                "security_private_reporting": False,
                "draft_pr_required": False,
                "discovery_evidence_allowed": True,
                "good_first_issue_ai_allowed": True,
            }
            snapshot = material_snapshot(packet)
            packet["materials"]["material_snapshot"] = snapshot
            packet["understanding"]["orientation"]["material_snapshot"] = snapshot
            packet["understanding"]["assessment"]["material_snapshot"] = snapshot
            packet_path = Path(directory) / "packet.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            current_diff = {key: packet["diff"][key] for key in PR_DIFF_FIELDS}
            current_diff["deletions"] = 2

            with patch("reviewworthy.action.capture_pr_diff", return_value=current_diff):
                result = check_packet(
                    packet_path,
                    current_diff=current_diff,
                    root=Path(directory),
                    event_name="pull_request",
                    event_base_sha="base-sha",
                    event_head_sha="head-sha",
                    mode="enforce",
                )

            self.assertIn("current_diff_deletions_mismatch", {violation["code"] for violation in result["violations"]})

    def test_individual_enforcement_flags_apply_in_report_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet_path.write_text(json.dumps(valid_packet()), encoding="utf-8")

            result = check_packet(packet_path, fail_on_unknown=True, require_current_diff=True)

            codes = {violation["code"] for violation in result["violations"]}
            self.assertEqual(result["mode"], "report")
            self.assertIn("current_diff_required", codes)
            self.assertIn("unknown_policy", codes)

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
            packet["ai_assistance"]["disclosure"] = {"text": "", "locations": [], "human_confirmed": False}
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            result = check_packet(path)
            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(result["unknowns"])

    def test_action_fails_explicit_disclosure_violation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"]["authoritative_claims"] = {
                "ai_assistance": "allowed",
                "issue_required": False,
                "disclosure_required": True,
                "disclosure_locations": ["pr_body"],
                "disclosure_stages": [],
                "human_pr_narrative_required": False,
                "security_private_reporting": False,
                "draft_pr_required": False,
                "discovery_evidence_allowed": True,
                "good_first_issue_ai_allowed": True,
            }
            packet["ai_assistance"]["disclosure"] = {"text": "", "locations": [], "human_confirmed": False}
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "failure")
            self.assertIn("missing_ai_disclosure", {violation["code"] for violation in result["violations"]})

    def test_action_fails_ai_prohibited_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"]["authoritative_claims"]["ai_assistance"] = "prohibited"
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "failure")
            self.assertIn("ai_assistance_prohibited", {violation["code"] for violation in result["violations"]})

    def test_action_reports_module_scope_as_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["contract"]["scope"] = {"modules": ["input boundary"]}
            packet["diff"]["changed_files"] = ["src/unapproved.py"]
            packet["contract"]["approval"]["contract_sha256"] = contract_snapshot(packet["contract"])
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(any("module-based" in unknown.lower() for unknown in result["unknowns"]))

    def test_action_keeps_mixed_scope_file_allowlist_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["contract"]["scope"] = {"files": ["src/example.py"], "modules": ["input boundary"]}
            packet["diff"]["changed_files"] = ["src/unapproved.py"]
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "failure")
            self.assertIn("out_of_scope_files", {violation["code"] for violation in result["violations"]})

    def test_action_reports_incomplete_explicit_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["policy"] = {"posture": "explicit", "authoritative_claims": {"ai_assistance": "allowed", "disclosure_required": False}}
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["orientation"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "success")
            self.assertTrue(any("incomplete" in unknown.lower() for unknown in result["unknowns"]))

    def test_action_handles_invalid_changed_file_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = valid_packet()
            packet["diff"]["changed_files"] = [{"path": "src/unapproved.py"}]
            packet["materials"]["material_snapshot"] = material_snapshot(packet)
            packet["understanding"]["assessment"]["material_snapshot"] = material_snapshot(packet)
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            result = check_packet(path)

            self.assertEqual(result["conclusion"], "failure")
            self.assertIn("invalid_changed_file", {violation["code"] for violation in result["violations"]})
