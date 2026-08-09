from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from reviewworthy.action import check_evidence, github_event_context
from reviewworthy.evidence import append_evidence_summary, build_evidence_summary, render_evidence_summary
from reviewworthy.git import PR_DIFF_FIELDS, capture_pr_diff

from helpers import valid_packet


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
        return append_evidence_summary("## Change\nA bounded change.", build_evidence_summary(packet, diff))

    def test_composite_action_reads_pr_body_and_never_reads_a_packet(self) -> None:
        content = (Path(__file__).parents[1] / "action.yml").read_text(encoding="utf-8")
        self.assertIn("python -m reviewworthy action check", content)
        self.assertIn("evidence-enforce", content)
        self.assertNotIn("Contribution Packet", content)
        self.assertNotIn("REVIEWWORTHY_PACKET", content)
        self.assertNotIn("gh pr create", content)
        self.assertNotIn("git fetch", content)

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

    def test_summary_with_missing_claim_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, diff = self._repository(Path(directory))
            summary = build_evidence_summary(valid_packet(), diff)
            summary["claims"].pop("ownership")
            with self.assertRaises(ValueError):
                render_evidence_summary(summary)

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
