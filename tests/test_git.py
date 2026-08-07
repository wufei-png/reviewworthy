from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reviewworthy.git import GitError, capture_diff, current_head, run_verification


class GitEvidenceTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        return completed.stdout.strip()

    def test_capture_diff_and_verification_bind_to_real_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            (root / "example.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "example.txt")
            self._git(root, "commit", "-qm", "base")
            base = current_head(root)
            (root / "example.txt").write_text("base\nhead\n", encoding="utf-8")
            self._git(root, "commit", "-qam", "head")
            head = current_head(root)

            diff = capture_diff(root, base, head)
            self.assertEqual(diff["base_sha"], base)
            self.assertEqual(diff["head_sha"], head)
            self.assertEqual(diff["changed_files"], ["example.txt"])
            self.assertEqual(diff["additions"], 1)
            self.assertEqual(diff["deletions"], 0)
            self.assertEqual(len(diff["patch_sha256"]), 64)

            receipt = run_verification(root, head, [sys.executable, "-c", "print('ok')"])
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["head_sha"], head)
            self.assertEqual(receipt["cwd"], str(root.resolve()))
            self.assertEqual(receipt["provenance"], "cli_executed")
            self.assertNotEqual(receipt["stdout_sha256"], receipt["stderr_sha256"])

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
