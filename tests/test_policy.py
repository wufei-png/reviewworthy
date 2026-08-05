from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from reviewworthy.policy import inspect_policy


class PolicyInspectionTests(unittest.TestCase):
    def test_repository_document_conflict_is_a_hard_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("AI assistance is not allowed. Open an issue first.\n", encoding="utf-8")
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text("[ai]\nallowed = true\n", encoding="utf-8")

            result = inspect_policy(root)

            self.assertEqual(result["authoritative_claims"]["ai_assistance"], "prohibited")
            self.assertEqual(result["authoritative_claims"]["issue_required"], True)
            self.assertEqual(result["result"], "blocked")
            self.assertEqual(result["hard_stops"][0]["code"], "policy_conflict")

    def test_structured_policy_fills_silent_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("A small example project.\n", encoding="utf-8")
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text(
                "[ai]\nallowed = true\ndisclosure_required = true\n[contribution]\nissue_required = true\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertEqual(result["result"], "passed")
            self.assertEqual(result["authoritative_claims"]["issue_required"], True)
            self.assertEqual(result["authoritative_claims"]["disclosure_required"], True)

    def test_missing_policy_is_conservative_but_not_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_policy(Path(directory))

            self.assertEqual(result["posture"], "conservative")
            self.assertEqual(result["conflicts"], [])
            self.assertEqual(result["hard_stops"], [])

    def test_explanatory_text_does_not_become_policy_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "Issue-backed and Discovery entries converge into one flow. "
                "The README explains why disclosure is recorded and why an issue may be useful.\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertIsNone(result["authoritative_claims"]["issue_required"])
            self.assertIsNone(result["authoritative_claims"]["disclosure_required"])

    def test_structured_disclosure_policy_is_normalized_with_locations_and_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("A small example project.\n", encoding="utf-8")
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text(
                "[ai]\nallowed = true\ndisclosure_required = true\ndisclosure_locations = ['commit_trailer']\ndisclosure_stages = ['verification']\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertEqual(result["authoritative_claims"]["disclosure_locations"], ["commit_trailer"])
            self.assertEqual(result["disclosure"]["stages"], ["verification"])
