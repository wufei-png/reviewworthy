from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
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
