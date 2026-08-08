from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reviewworthy.git import GitError, capture_pr_diff, current_head, run_verification


class GitEvidenceTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        return completed.stdout.strip()

    def test_verification_binds_to_real_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            (root / "example.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "example.txt")
            self._git(root, "commit", "-qm", "base")
            (root / "example.txt").write_text("base\nhead\n", encoding="utf-8")
            self._git(root, "commit", "-qam", "head")
            head = current_head(root)

            receipt = run_verification(root, head, [sys.executable, "-c", "print('ok')"])
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["head_sha"], head)
            self.assertEqual(receipt["cwd"], ".")
            self.assertEqual(receipt["head_sha_before"], head)
            self.assertEqual(receipt["head_sha_after"], head)
            self.assertTrue(receipt["worktree_clean_before"])
            self.assertTrue(receipt["worktree_clean_after"])
            self.assertEqual(receipt["status"], "valid")
            self.assertEqual(receipt["provenance"], "cli_executed")
            self.assertNotEqual(receipt["stdout_sha256"], receipt["stderr_sha256"])

    def test_capture_pr_diff_attributes_only_changes_since_merge_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            self._git(root, "branch", "-M", "main")
            (root / "common.txt").write_text("common\n", encoding="utf-8")
            self._git(root, "add", "common.txt")
            self._git(root, "commit", "-qm", "common base")
            merge_base = current_head(root)

            self._git(root, "checkout", "-qb", "feature")
            (root / "only-feature.txt").write_text("feature\n", encoding="utf-8")
            self._git(root, "add", "only-feature.txt")
            self._git(root, "commit", "-qm", "feature change")
            head = current_head(root)

            self._git(root, "checkout", "-q", "main")
            (root / "only-main.txt").write_text("main\n", encoding="utf-8")
            self._git(root, "add", "only-main.txt")
            self._git(root, "commit", "-qm", "main change")
            base_tip = current_head(root)

            diff = capture_pr_diff(root, "main", "feature")

            self.assertEqual(diff["comparison"], "merge_base")
            self.assertEqual(diff["base_tip_sha"], base_tip)
            self.assertEqual(diff["merge_base_sha"], merge_base)
            self.assertEqual(diff["head_sha"], head)
            self.assertEqual(diff["changed_files"], ["only-feature.txt"])
            self.assertEqual(diff["additions"], 1)
            self.assertEqual(diff["deletions"], 0)
            self.assertEqual(len(diff["patch_sha256"]), 64)

    def test_verification_refuses_when_worktree_head_moves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            (root / "example.txt").write_text("one\n", encoding="utf-8")
            self._git(root, "add", "example.txt")
            self._git(root, "commit", "-qm", "one")
            expected = current_head(root)
            (root / "example.txt").write_text("two\n", encoding="utf-8")
            self._git(root, "commit", "-qam", "two")

            with self.assertRaises(GitError):
                run_verification(root, expected, [sys.executable, "-c", "pass"])

    def test_verification_refuses_dirty_worktree_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            (root / "example.txt").write_text("one\n", encoding="utf-8")
            self._git(root, "add", "example.txt")
            self._git(root, "commit", "-qm", "one")
            expected = current_head(root)
            (root / "example.txt").write_text("dirty\n", encoding="utf-8")

            with self.assertRaisesRegex(GitError, "clean worktree"):
                run_verification(root, expected, [sys.executable, "-c", "raise SystemExit(99)"])

    def test_verification_records_invalid_receipt_when_command_dirties_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            (root / "example.txt").write_text("one\n", encoding="utf-8")
            self._git(root, "add", "example.txt")
            self._git(root, "commit", "-qm", "one")
            expected = current_head(root)

            receipt = run_verification(
                root,
                expected,
                [sys.executable, "-c", "from pathlib import Path; Path('created.txt').write_text('unexpected')"],
            )

            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["status"], "invalid")
            self.assertFalse(receipt["worktree_clean_after"])
            self.assertEqual(receipt["head_sha_before"], expected)
            self.assertEqual(receipt["head_sha_after"], expected)
            self.assertEqual(receipt["failure_reason"], "worktree_dirty_after_execution")

    def test_verification_records_invalid_receipt_when_command_moves_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            (root / "example.txt").write_text("one\n", encoding="utf-8")
            self._git(root, "add", "example.txt")
            self._git(root, "commit", "-qm", "one")
            expected = current_head(root)
            command = (
                "from pathlib import Path; import subprocess; "
                "Path('example.txt').write_text('two\\n'); "
                "subprocess.run(['git', 'add', 'example.txt'], check=True); "
                "subprocess.run(['git', 'commit', '-qm', 'two'], check=True)"
            )

            receipt = run_verification(root, expected, [sys.executable, "-c", command])

            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["status"], "invalid")
            self.assertEqual(receipt["head_sha_before"], expected)
            self.assertNotEqual(receipt["head_sha_after"], expected)
            self.assertEqual(receipt["failure_reason"], "head_changed_after_execution")
