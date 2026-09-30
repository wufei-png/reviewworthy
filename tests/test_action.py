from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from reviewworthy.action import check_evidence, github_event_context
from reviewworthy.evidence import (
    OVERVIEW_END,
    OVERVIEW_START,
    append_evidence_summary,
    build_evidence_summary,
    extract_evidence_summary,
    render_evidence_summary,
    validate_evidence_summary,
)
from reviewworthy.git import GitError, PR_DIFF_FIELDS, capture_pr_diff
from reviewworthy.policy import PolicyTreeError
from reviewworthy.util import run_bounded

from helpers import valid_packet


def run_wrapper(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    repository = Path(__file__).parents[1]
    content = (repository / "action.yml").read_text(encoding="utf-8")
    script = textwrap.dedent(content.split("      run: |\n", 1)[1])
    return subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", script],
        cwd=root,
        env={"PYTHONPATH": str(repository / "src"), **env},
        capture_output=True,
        text=True,
        timeout=30,
    )


class ActionWrapperTests(unittest.TestCase):
    def test_wrapper_reports_missing_or_unusable_prerequisites_before_import(self) -> None:
        cases = (
            ("missing_python", "python must be available"),
            ("old_python", "Python >=3.11 is required"),
            ("broken_python", "Python >=3.11 is required"),
            ("missing_git", "Git must be available"),
            ("broken_git", "Git must be available"),
        )
        for mode in ("report", "evidence-enforce"):
            for case, message in cases:
                with self.subTest(mode=mode, case=case), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    if case == "old_python":
                        shim = root / "python"
                        shim.write_text(
                            f"#!{sys.executable}\nimport sys\n"
                            "assert sys.argv[1] == '-c', 'package import reached'\n"
                            "sys.version_info = (3, 10, 0)\nexec(sys.argv[2])\n",
                            encoding="utf-8",
                        )
                        shim.chmod(0o755)
                    elif case == "broken_python":
                        shim = root / "python"
                        shim.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
                        shim.chmod(0o755)
                    elif case != "missing_python":
                        (root / "python").symlink_to(sys.executable)
                    if case == "broken_git":
                        shim = root / "git"
                        shim.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
                        shim.chmod(0o755)
                    result = run_wrapper(root, {"PATH": str(root), "REVIEWWORTHY_MODE": mode})
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("prerequisite error", result.stderr)
                    self.assertIn(message, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_usable_runtime_keeps_report_findings_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "python").symlink_to(sys.executable)
            (root / "git").symlink_to(shutil.which("git"))
            result = run_wrapper(root, {"PATH": str(root), "REVIEWWORTHY_MODE": "report"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["unknowns"])

    def test_ci_dependencies_are_immutable_and_checkout_has_no_credentials(self) -> None:
        root = Path(__file__).parents[1]
        workflow = (root / ".github/workflows/reviewworthy.yml").read_text(encoding="utf-8")
        dependencies = re.findall(r"uses: (actions/[^\s]+)", workflow)
        self.assertEqual(len(dependencies), 2)
        for dependency in dependencies:
            self.assertRegex(dependency, r"^actions/(checkout|setup-python)@[0-9a-f]{40}$")
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertNotIn("uses:", (root / "action.yml").read_text(encoding="utf-8"))


class ActionEvidenceTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        return completed.stdout.strip()

    def _repository(self, root: Path) -> tuple[Path, dict]:
        repository = root / "repository"
        repository.mkdir()
        self._git(repository, "init", "-q")
        self._git(repository, "config", "user.email", "test@example.invalid")
        self._git(repository, "config", "user.name", "Reviewworthy Test")
        self._git(repository, "branch", "-M", "main")
        (repository / "src").mkdir()
        (repository / "src" / "example.py").write_text("one\n", encoding="utf-8")
        self._git(repository, "add", "src/example.py")
        self._git(repository, "commit", "-qm", "base")
        self._git(repository, "checkout", "-qb", "feature")
        (repository / "src" / "example.py").write_text("one\ntwo\n", encoding="utf-8")
        self._git(repository, "commit", "-qam", "feature")
        return repository, capture_pr_diff(repository, "main", "feature")

    def _body(self, diff: dict) -> str:
        packet = valid_packet()
        packet["diff"] = dict(diff)
        packet["verification"]["receipts"][0].update({
            "subject_digest": diff["subject_digest"],
            "head_sha": diff["head_sha"],
            "head_sha_before": diff["head_sha"],
            "head_sha_after": diff["head_sha"],
        })
        return append_evidence_summary("## Change\nA bounded change.", build_evidence_summary(packet, diff))

    def _policy_repository(self, root: Path, readme: str, structured: str | None = None) -> tuple[Path, dict]:
        repository = root / "policy-repository"
        repository.mkdir()
        self._git(repository, "init", "-q")
        self._git(repository, "config", "user.email", "test@example.invalid")
        self._git(repository, "config", "user.name", "Reviewworthy Test")
        self._git(repository, "branch", "-M", "main")
        (repository / "README.md").write_text(readme, encoding="utf-8")
        (repository / "src").mkdir()
        (repository / "src" / "example.py").write_text("one\n", encoding="utf-8")
        if structured is not None:
            (repository / ".reviewworthy").mkdir()
            (repository / ".reviewworthy" / "policy.toml").write_text(structured, encoding="utf-8")
        self._git(repository, "add", ".")
        self._git(repository, "commit", "-qm", "base policy")
        self._git(repository, "checkout", "-qb", "feature")
        (repository / "src" / "example.py").write_text("one\ntwo\n", encoding="utf-8")
        self._git(repository, "commit", "-qam", "feature")
        return repository, capture_pr_diff(repository, "main", "feature")

    def test_composite_action_reads_pr_body_and_never_reads_a_packet(self) -> None:
        content = (Path(__file__).parents[1] / "action.yml").read_text(encoding="utf-8")
        self.assertIn("python -m reviewworthy action check", content)
        self.assertIn("evidence-enforce", content)
        self.assertNotIn("Contribution Packet", content)
        self.assertNotIn("REVIEWWORTHY_PACKET", content)
        self.assertNotIn("gh pr create", content)
        self.assertNotIn("git fetch", content)

    def test_ci_smoke_tests_the_composite_action_wrapper(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "reviewworthy.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("uses: ./", workflow)
        self.assertIn("mode: report", workflow)

    def test_event_context_includes_runner_owned_pr_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "event.json"
            event_path.write_text(json.dumps({
                "repository": {"full_name": "Example/Project", "id": 101},
                "pull_request": {
                    "base": {"sha": "base"},
                    "head": {"sha": "head"},
                    "body": "current body",
                },
            }), encoding="utf-8")
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event_path)}, clear=False):
                self.assertEqual(
                    github_event_context(),
                    ("pull_request", "Example/Project", 101, "base", "head", "current body"),
                )

    def test_wrapper_rejects_malformed_event_json_and_shapes(self) -> None:
        events = (
            "{",
            "[]",
            '{"pull_request": []}',
            '{"repository": [], "pull_request": {"base": [], "head": true}}',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "python").symlink_to(sys.executable)
            (root / "git").symlink_to(shutil.which("git"))
            event_path = root / "event.json"
            for event in events:
                for mode in ("report", "evidence-enforce"):
                    with self.subTest(event=event, mode=mode):
                        event_path.write_text(event, encoding="utf-8")
                        result = run_wrapper(root, {
                            "PATH": str(root), "REVIEWWORTHY_MODE": mode,
                            "GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event_path),
                        })
                        payload = json.loads(result.stdout)
                        self.assertEqual(result.returncode, 1 if mode == "evidence-enforce" else 0, result.stderr)
                        self.assertEqual(payload["checked"], False)
                        if mode == "evidence-enforce":
                            self.assertEqual({item["code"] for item in payload["violations"]}, {"evidence_summary_required"})

    def test_wrapper_enforces_fixture_event_and_stays_read_only_with_missing_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, diff = self._repository(root)
            tools = root / "tools"
            tools.mkdir()
            (tools / "python").symlink_to(sys.executable)
            calls = root / "git-calls.jsonl"
            git = tools / "git"
            git.write_text(
                f"#!{sys.executable}\nimport json, subprocess, sys\n"
                f"with open({str(calls)!r}, 'a') as log: log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                f"sys.exit(subprocess.run([{shutil.which('git')!r}, *sys.argv[1:]]).returncode)\n",
                encoding="utf-8",
            )
            git.chmod(0o755)
            provider_call = root / "provider-called"
            gh = tools / "gh"
            gh.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(provider_call)!r}).touch()\nraise SystemExit(1)\n", encoding="utf-8")
            gh.chmod(0o755)
            # Poison private state: the Action must use only the public Body.
            private = repository / ".git/reviewworthy/v0.3/contributions/action-fixture/packet.json"
            private.parent.mkdir(parents=True)
            private.write_text("invalid private Packet", encoding="utf-8")
            event = {
                "repository": {"full_name": "example/project", "id": 101},
                "pull_request": {
                    "base": {"sha": diff["base_tip_sha"]},
                    "head": {"sha": diff["head_sha"]}, "body": self._body(diff),
                },
            }
            event_path = root / "event.json"
            for missing_base in (False, True):
                if missing_base:
                    event["pull_request"]["base"]["sha"] = "0" * 40
                event_path.write_text(json.dumps(event), encoding="utf-8")
                for mode in ("report", "evidence-enforce"):
                    with self.subTest(missing_base=missing_base, mode=mode):
                        result = run_wrapper(repository, {
                            "PATH": str(tools), "REVIEWWORTHY_MODE": mode,
                            "GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event_path),
                        })
                        payload = json.loads(result.stdout)
                        failed = missing_base and mode == "evidence-enforce"
                        self.assertEqual(result.returncode, 1 if failed else 0, result.stderr)
                        if failed:
                            self.assertEqual({item["code"] for item in payload["violations"]}, {"base_policy_unavailable", "current_diff_unavailable"})
            self.assertFalse(provider_call.exists())
            self.assertEqual(private.read_text(encoding="utf-8"), "invalid private Packet")
            commands = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
            for command in commands:
                verb = command[2] if command[:1] == ["-C"] else command[0]
                self.assertIn(verb, {"--version", "rev-parse", "ls-tree", "cat-file", "merge-base", "diff"}, command)

    def test_base_policy_diagnostics_reach_action_modes_from_fixture_events(self) -> None:
        cases = (
            ("invalid_configuration", "base_policy_invalid_configuration"),
            ("encoding", "base_policy_source_encoding"),
            ("oversized", "base_policy_source_limit"),
            ("symlink", "base_policy_source_unsupported"),
            ("unreadable", "base_policy_source_unreadable"),
        )
        for case, code in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                structured = '[ai]\nallowed = "invalid"\n' if case == "invalid_configuration" else '[ai]\nallowed = true\n'
                repository, _ = self._policy_repository(root, "Project policy.\n", structured)
                readme = repository / "README.md"
                if case == "encoding":
                    readme.write_bytes(b"\xff\x00")
                elif case == "oversized":
                    readme.write_bytes(b"x" * (1024 * 1024 + 1))
                elif case == "symlink":
                    readme.unlink()
                    readme.symlink_to("src/example.py")
                self._git(repository, "add", ".")
                self._git(repository, "commit", "--allow-empty", "-qm", "base input fixture")
                self._git(repository, "branch", "-f", "main", "HEAD")
                readme_blob = self._git(repository, "rev-parse", "main:README.md")
                (repository / "src/example.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
                self._git(repository, "commit", "-qam", "new head")
                diff = capture_pr_diff(repository, "main", "feature")
                event_path = root / "event.json"
                event_path.write_text(json.dumps({
                    "repository": {"full_name": "example/project", "id": 101},
                    "pull_request": {
                        "base": {"sha": diff["base_tip_sha"]},
                        "head": {"sha": diff["head_sha"]}, "body": self._body(diff),
                    },
                }), encoding="utf-8")

                def read_base(args: list[str], **kwargs: object) -> object:
                    if case == "unreadable" and args[-3:] == ["cat-file", "blob", readme_blob]:
                        raise OSError("fixture base blob is unreadable")
                    return run_bounded(args, **kwargs)

                with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event_path)}), patch("reviewworthy.policy.run_bounded", side_effect=read_base):
                    name, slug, repo_id, base, head, body = github_event_context()
                    for mode in ("report", "evidence-enforce"):
                        result = check_evidence(body, root=repository, event_name=name, event_repository=slug, event_repository_id=repo_id, event_base_sha=base, event_head_sha=head, mode=mode)
                        self.assertEqual(result["base_policy"]["machine_authority"], {})
                        self.assertTrue(result["base_policy"]["diagnostics"])
                        if mode == "evidence-enforce":
                            self.assertEqual(result["conclusion"], "failure")
                            self.assertIn(code, {item["code"] for item in result["violations"]})
                        else:
                            self.assertEqual(result["conclusion"], "success")
                            self.assertTrue(result["unknowns"])

    def test_enforcement_rejects_incomplete_runner_context(self) -> None:
        body = append_evidence_summary(
            "Body",
            build_evidence_summary(valid_packet(), valid_packet()["diff"]),
        )

        result = check_evidence(
            body,
            root=Path("."),
            event_name="push",
            event_repository=None,
            event_repository_id=None,
            event_base_sha=None,
            event_head_sha=None,
            mode="evidence-enforce",
        )

        self.assertEqual(result["conclusion"], "failure")
        self.assertTrue(result["checked"])
        self.assertEqual(
            {item["code"] for item in result["violations"]},
            {
                "base_policy_unavailable",
                "pull_request_context_required",
                "repository_context_required",
                "pull_request_commits_required",
            },
        )

    def test_enforcement_rejects_unavailable_current_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            with patch("reviewworthy.action.capture_pr_diff", side_effect=GitError("missing Git objects")):
                result = check_evidence(
                    self._body(diff),
                    root=repository,
                    event_name="pull_request",
                    event_repository="example/project",
                    event_repository_id=101,
                    event_base_sha=diff["base_tip_sha"],
                    event_head_sha=diff["head_sha"],
                    mode="evidence-enforce",
                )

        self.assertEqual(result["conclusion"], "failure")
        self.assertIn("current_diff_unavailable", {item["code"] for item in result["violations"]})

    def test_report_treats_missing_summary_as_unknown_but_enforcement_fails(self) -> None:
        report = check_evidence(
            "plain body",
            root=Path("."),
            event_name="pull_request",
            event_repository="example/project",
            event_repository_id=101,
            event_base_sha="base",
            event_head_sha="head",
        )
        enforced = check_evidence(
            "plain body",
            root=Path("."),
            event_name="pull_request",
            event_repository="example/project",
            event_repository_id=101,
            event_base_sha="base",
            event_head_sha="head",
            mode="evidence-enforce",
        )
        self.assertEqual(report["conclusion"], "success")
        self.assertTrue(report["unknowns"])
        self.assertEqual(enforced["conclusion"], "failure")
        self.assertEqual({item["code"] for item in enforced["violations"]}, {"evidence_summary_required"})

    def test_real_pr_summary_passes_and_claims_are_not_verified_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            result = check_evidence(
                self._body(diff),
                root=repository,
                event_name="pull_request",
                event_repository="EXAMPLE/PROJECT",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )
        self.assertEqual(result["conclusion"], "success", result["violations"])
        self.assertEqual(result["verified_facts"]["diff"]["subject_digest"], diff["subject_digest"])
        self.assertNotIn("verification", result["verified_facts"])
        self.assertEqual(result["contributor_claims"]["verification"]["claimed_outcome"], "passed")

    def test_report_mode_keeps_mismatched_summary_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            result = check_evidence(
                self._body(diff),
                root=repository,
                event_name="pull_request",
                event_repository="other/project",
                event_repository_id=999,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="report",
            )

        self.assertEqual(result["conclusion"], "success")
        self.assertIn("repository_identity_mismatch", {item["code"] for item in result["violations"]})

    def test_action_uses_only_structured_policy_from_the_base_as_positive_machine_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._policy_repository(
                Path(directory),
                "AI assistance is allowed.\n",
                "[ai]\nallowed = true\ndisclosure_required = true\n",
            )
            (repository / "README.md").write_text("AI assistance is prohibited.\n", encoding="utf-8")
            (repository / ".reviewworthy" / "policy.toml").write_text("[ai]\nallowed = false\n", encoding="utf-8")
            self._git(repository, "add", ".")
            self._git(repository, "commit", "-qm", "untrusted head policy")
            diff = capture_pr_diff(repository, "main", "feature")

            result = check_evidence(
                self._body(diff),
                root=repository,
                event_name="pull_request",
                event_repository="example/project",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )

        self.assertEqual(result["conclusion"], "success", result["violations"])
        self.assertEqual(result["base_policy"]["machine_authority"]["ai_assistance"], "allowed")
        self.assertTrue(result["base_policy"]["document_advisory"])

    def test_explicit_document_prohibition_in_base_blocks_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._policy_repository(Path(directory), "AI assistance is prohibited.\n")
            result = check_evidence(
                self._body(diff),
                root=repository,
                event_name="pull_request",
                event_repository="example/project",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )

        self.assertIn("base_policy_ai_prohibited", {item["code"] for item in result["violations"]})
        self.assertEqual(result["base_policy"]["machine_authority"], {})

    def test_base_policy_conflict_blocks_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._policy_repository(
                Path(directory),
                "AI assistance is prohibited.\n",
                "[ai]\nallowed = true\n",
            )

            result = check_evidence(
                self._body(diff),
                root=repository,
                event_name="pull_request",
                event_repository="example/project",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )

        self.assertEqual(result["conclusion"], "failure")
        self.assertIn("base_policy_conflict", {item["code"] for item in result["violations"]})

    def test_base_policy_ambiguity_blocks_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._policy_repository(
                Path(directory),
                "AI assistance is allowed.\nAI assistance is prohibited.\n",
            )

            result = check_evidence(
                self._body(diff),
                root=repository,
                event_name="pull_request",
                event_repository="example/project",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )

        self.assertEqual(result["conclusion"], "failure")
        self.assertIn("base_policy_ambiguity", {item["code"] for item in result["violations"]})

    def test_unavailable_base_policy_blocks_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            with patch(
                "reviewworthy.action.inspect_policy_at_commit",
                side_effect=PolicyTreeError("base policy could not be read"),
            ):
                result = check_evidence(
                    self._body(diff),
                    root=repository,
                    event_name="pull_request",
                    event_repository="example/project",
                    event_repository_id=101,
                    event_base_sha=diff["base_tip_sha"],
                    event_head_sha=diff["head_sha"],
                    mode="evidence-enforce",
                )

        self.assertEqual(result["conclusion"], "failure")
        self.assertIn("base_policy_unavailable", {item["code"] for item in result["violations"]})

    def test_required_base_policy_disclosure_blocks_missing_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._policy_repository(
                Path(directory),
                "AI assistance is allowed.\n",
                "[ai]\nallowed = true\ndisclosure_required = true\n",
            )
            packet = valid_packet()
            packet["ai_assistance"]["disclosure"]["text"] = ""
            body = append_evidence_summary("Body", build_evidence_summary(packet, diff))

            result = check_evidence(
                body,
                root=repository,
                event_name="pull_request",
                event_repository="example/project",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )

        self.assertEqual(result["conclusion"], "failure")
        self.assertIn("base_policy_disclosure_required", {item["code"] for item in result["violations"]})

    def test_each_public_diff_identity_field_is_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            for field in (field for field in PR_DIFF_FIELDS if field != "comparison"):
                packet = valid_packet()
                declared = dict(diff)
                value = declared[field]
                if isinstance(value, str):
                    declared[field] = "other"
                elif isinstance(value, list):
                    declared[field] = [*value, "other.txt"]
                else:
                    declared[field] = value + 1
                if field == "fingerprint_algorithm":
                    body = self._body(diff).replace("git-raw-content-v1", "legacy-patch-v1")
                else:
                    body = append_evidence_summary("Body", build_evidence_summary(packet, declared))
                result = check_evidence(
                    body,
                    root=repository,
                    event_name="pull_request",
                    event_repository="example/project",
                    event_repository_id=101,
                    event_base_sha=diff["base_tip_sha"],
                    event_head_sha=diff["head_sha"],
                    mode="evidence-enforce",
                )
                expected = "evidence_summary_required" if field == "fingerprint_algorithm" else f"current_diff_{field}_mismatch"
                self.assertIn(expected, {item["code"] for item in result["violations"]}, field)

    def test_duplicate_summary_markers_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            body = self._body(diff)
            result = check_evidence(
                body + "\n\n" + body,
                root=repository,
                event_name="pull_request",
                event_repository="example/project",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )
        self.assertEqual({item["code"] for item in result["violations"]}, {"evidence_summary_required"})

    def test_human_overview_preserves_machine_summary_and_labels_claims(self) -> None:
        packet = valid_packet()
        summary = build_evidence_summary(packet, packet["diff"])

        body = append_evidence_summary("## Change\nA bounded change.", summary, workflow_ready=True)

        self.assertIn(OVERVIEW_START, body)
        self.assertIn(OVERVIEW_END, body)
        self.assertIn("**Contributor workflow:** Ready for maintainer review", body)
        self.assertIn("**Scope:** 1 changed file, +3 / -1 lines", body)
        self.assertIn("Contributor claims 1 current verification receipt passed.", body)
        self.assertIn("remain contributor claims", body)
        self.assertEqual(extract_evidence_summary(body), summary)

    def test_human_overview_does_not_claim_readiness_when_not_established(self) -> None:
        packet = valid_packet()
        summary = build_evidence_summary(packet, packet["diff"])

        body = append_evidence_summary("Body", summary, workflow_ready=False)

        self.assertIn("**Contributor workflow:** Not yet ready for maintainer review", body)

    def test_existing_human_overview_marker_is_rejected(self) -> None:
        packet = valid_packet()
        summary = build_evidence_summary(packet, packet["diff"])

        with self.assertRaisesRegex(ValueError, "already contains"):
            append_evidence_summary(f"Body\n{OVERVIEW_START}", summary, workflow_ready=True)

    def test_action_rejects_duplicate_human_overviews(self) -> None:
        packet = valid_packet()
        summary = build_evidence_summary(packet, packet["diff"])
        body = append_evidence_summary("Body", summary, workflow_ready=True)
        duplicated = body.replace(OVERVIEW_END, f"{OVERVIEW_END}\n{OVERVIEW_START}\nConflicting overview\n{OVERVIEW_END}")

        result = check_evidence(
            duplicated,
            root=Path("."),
            event_name="pull_request",
            event_repository="example/project",
            event_repository_id=101,
            event_base_sha="base",
            event_head_sha="head",
            mode="evidence-enforce",
        )

        self.assertEqual(result["conclusion"], "failure")
        self.assertEqual({item["code"] for item in result["violations"]}, {"evidence_summary_required"})

    def test_summary_with_missing_claim_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            summary = build_evidence_summary(valid_packet(), diff)
            summary["claims"].pop("ownership")
            with self.assertRaises(ValueError):
                render_evidence_summary(summary)

    def test_summary_claims_are_closed_and_typed(self) -> None:
        summary = build_evidence_summary(valid_packet(), valid_packet()["diff"])
        summary["claims"]["verification"]["private_packet_path"] = ".reviewworthy/private/packet.json"
        summary["claims"]["ownership"]["profile"] = "custom"
        summary["claims"]["ai_disclosure"]["claimed_present"] = "yes"

        codes = {error["code"] for error in validate_evidence_summary(summary)["errors"]}

        self.assertIn("unknown_summary_field", codes)
        self.assertIn("invalid_summary_profile", codes)
        self.assertIn("invalid_summary_disclosure_claim", codes)

    def test_summary_verification_claim_and_count_must_agree(self) -> None:
        summary = build_evidence_summary(valid_packet(), valid_packet()["diff"])
        summary["claims"]["verification"] = {"claimed_outcome": "not_recorded", "receipt_count": 1}

        self.assertIn(
            "inconsistent_summary_verification_claim",
            {error["code"] for error in validate_evidence_summary(summary)["errors"]},
        )

    def test_old_receipt_is_not_recognized_as_a_public_verification_claim(self) -> None:
        packet = valid_packet()
        packet["verification"]["receipts"] = [{"exit_code": 0, "status": "valid", "provenance": "cli_executed"}]

        summary = build_evidence_summary(packet, packet["diff"])

        self.assertEqual(summary["claims"]["verification"], {"claimed_outcome": "not_recorded", "receipt_count": 0})

    def test_repository_identity_mismatch_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            result = check_evidence(
                self._body(diff),
                root=repository,
                event_name="pull_request",
                event_repository="other/project",
                event_repository_id=202,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )
        self.assertIn("repository_identity_mismatch", {item["code"] for item in result["violations"]})

    def test_base_policy_input_failures_block_enforcement_and_report_without_head_authority(self) -> None:
        for mode in ("evidence-enforce", "report"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                repository, diff = self._policy_repository(Path(directory), "AI assistance is allowed.\n", '[ai]\nallowed = true\n[discovery]\nauthoritative_documents = ["docs/contributing.md"]\n')
                (repository / "docs").mkdir()
                (repository / "docs/contributing.md").write_text("AI assistance is allowed.\n", encoding="utf-8")
                self._git(repository, "add", ".")
                self._git(repository, "commit", "-qm", "head cannot repair base policy")
                diff = capture_pr_diff(repository, "main", "feature")
                result = check_evidence(self._body(diff), root=repository, event_name="pull_request", event_repository="example/project", event_repository_id=101, event_base_sha=diff["base_tip_sha"], event_head_sha=diff["head_sha"], mode=mode)
                self.assertEqual(result["base_policy"]["machine_authority"], {})
                self.assertEqual(result["base_policy"]["diagnostics"][0]["path"], "docs/contributing.md")
                self.assertNotIn("AI assistance is allowed", json.dumps(result["base_policy"]))
                if mode == "evidence-enforce":
                    self.assertEqual(result["conclusion"], "failure")
                    self.assertIn("base_policy_source_missing", {item["code"] for item in result["violations"]})
                else:
                    self.assertEqual(result["conclusion"], "success")
                    self.assertTrue(any("source does not exist" in value for value in result["unknowns"]))

    def test_action_recomputes_unusual_paths_without_quote_path_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, _ = self._repository(Path(directory))
            name = "src/规则\tnewline\n.py"
            (repository / name).write_text("extra\n", encoding="utf-8")
            self._git(repository, "add", ".")
            self._git(repository, "commit", "-qm", "unusual path")
            self._git(repository, "config", "core.quotePath", "true")
            diff = capture_pr_diff(repository, "main", "feature")
            body = self._body(diff)
            self._git(repository, "config", "core.quotePath", "false")
            result = check_evidence(body, root=repository, event_name="pull_request", event_repository="example/project", event_repository_id=101, event_base_sha=diff["base_tip_sha"], event_head_sha=diff["head_sha"], mode="evidence-enforce")
            self.assertEqual(result["conclusion"], "success", result["violations"])
            self.assertIn(name, result["verified_facts"]["diff"]["changed_files"])
