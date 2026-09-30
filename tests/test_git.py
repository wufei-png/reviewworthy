from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reviewworthy.git import PR_DIFF_FIELDS, GitError, capture_bindable_pr_diff, capture_pr_diff, current_head, run_verification
from reviewworthy.packet import deterministic_evidence_checks

from helpers import valid_packet


class GitEvidenceTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        return completed.stdout.strip()

    def _verify(self, root: Path, head: str, argv: list[str], *, cwd: str = ".") -> dict:
        return run_verification(
            root,
            head,
            argv,
            check_id="unit",
            plan_digest="plan-digest",
            subject_digest="subject-digest",
            cwd=cwd,
        )

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

            receipt = self._verify(root, head, [sys.executable, "-c", "print('ok')"])
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["head_sha"], head)
            self.assertEqual(receipt["cwd"], ".")
            self.assertEqual(receipt["head_sha_before"], head)
            self.assertEqual(receipt["head_sha_after"], head)
            self.assertTrue(receipt["worktree_clean_before"])
            self.assertTrue(receipt["worktree_clean_after"])
            self.assertEqual(receipt["integrity_status"], "stable")
            self.assertEqual(receipt["command_outcome"], "passed")
            self.assertEqual(receipt["provenance"], "contributor_local")
            self.assertNotEqual(receipt["stdout_sha256"], receipt["stderr_sha256"])

    def test_verification_records_nested_cwd_as_repository_relative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            (root / "nested").mkdir()
            (root / "nested" / "example.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "nested/example.txt")
            self._git(root, "commit", "-qm", "base")

            receipt = self._verify(
                root,
                current_head(root),
                [sys.executable, "-c", "from pathlib import Path; assert Path('example.txt').is_file()"],
                cwd="nested",
            )

            self.assertEqual(receipt["cwd"], "nested")

    def test_verification_rejects_noncanonical_cwd_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            (root / "nested").mkdir()
            (root / "example.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "base")

            with self.assertRaises(ValueError):
                self._verify(root, current_head(root), [sys.executable, "-c", "print('should not run')"], cwd="./nested")

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
            self.assertEqual(len(diff["subject_digest"]), 64)
            self.assertEqual(diff["fingerprint_algorithm"], "git-raw-content-v1")

    def test_subject_digest_is_stable_when_only_commit_identity_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            self._git(root, "branch", "-M", "main")
            (root / "example.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "example.txt")
            self._git(root, "commit", "-qm", "base")
            self._git(root, "checkout", "-qb", "feature")
            (root / "example.txt").write_text("base\nchange\n", encoding="utf-8")
            self._git(root, "commit", "-qam", "first identity")
            before = capture_pr_diff(root, "main", "feature")

            self._git(root, "commit", "--amend", "-qm", "second identity")
            after = capture_pr_diff(root, "main", "feature")

            self.assertNotEqual(before["head_sha"], after["head_sha"])
            self.assertEqual(before["subject_digest"], after["subject_digest"])

    def test_bindable_diff_requires_current_clean_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            self._git(root, "branch", "-M", "main")
            (root / "example.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "example.txt")
            self._git(root, "commit", "-qm", "base")
            self._git(root, "checkout", "-qb", "feature")
            (root / "example.txt").write_text("base\nfeature\n", encoding="utf-8")
            self._git(root, "commit", "-qam", "feature")

            diff = capture_bindable_pr_diff(root, "main", "HEAD")
            self.assertEqual(diff["head_sha"], current_head(root))

            (root / "example.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(GitError, "clean worktree"):
                capture_bindable_pr_diff(root, "main", "HEAD")
            self._git(root, "checkout", "--", "example.txt")
            self._git(root, "checkout", "-q", "main")
            with self.assertRaisesRegex(GitError, "HEAD moved"):
                capture_bindable_pr_diff(root, "main", "feature")

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
                self._verify(root, expected, [sys.executable, "-c", "pass"])

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
                self._verify(root, expected, [sys.executable, "-c", "raise SystemExit(99)"])

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

            receipt = self._verify(
                root,
                expected,
                [sys.executable, "-c", "from pathlib import Path; Path('created.txt').write_text('unexpected')"],
            )

            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["integrity_status"], "invalid")
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

            receipt = self._verify(root, expected, [sys.executable, "-c", command])

            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["integrity_status"], "invalid")
            self.assertEqual(receipt["head_sha_before"], expected)
            self.assertNotEqual(receipt["head_sha_after"], expected)
            self.assertEqual(receipt["failure_reason"], "head_changed_after_execution")

    def test_nul_paths_counts_and_scope_are_independent_of_quote_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            self._git(root, "branch", "-M", "main")
            removed = "删除\t文件.txt"
            modified = "mod\nline.txt"
            added = "src/规则\t新\n'x [ok];$().py"
            for name, content in ((removed, "one\ntwo\nthree\n"), ("move old.txt", "move\ncontent\n"), (modified, "base\n")):
                (root / name).write_text(content, encoding="utf-8")
            (root / "binary.dat").write_bytes(b"\0before")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "base")
            self._git(root, "checkout", "-qb", "feature")
            (root / removed).unlink()
            (root / "move old.txt").rename(root / "move new.txt")
            (root / modified).write_text("base\nhead\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / added).write_text("new\ncontent\n", encoding="utf-8")
            (root / " name ").write_text("spaces\n", encoding="utf-8")
            (root / "binary.dat").write_bytes(b"\0after")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "paths")
            expected = sorted([removed, modified, added, "move old.txt", "move new.txt", "binary.dat", " name "])
            snapshots = []
            for setting in ("true", "false"):
                self._git(root, "config", "core.quotePath", setting)
                diff = capture_pr_diff(root, "main", "feature")
                self.assertEqual(diff["changed_files"], expected)
                self.assertEqual((diff["additions"], diff["deletions"]), (6, 5))
                self.assertEqual(diff["fingerprint_algorithm"], "git-raw-content-v1")
                snapshots.append({field: diff[field] for field in PR_DIFF_FIELDS})
                packet = valid_packet()
                packet["diff"] = diff
                packet["contract"]["scope"]["files"] = expected
                self.assertEqual(deterministic_evidence_checks(packet, strict=True), ([], []))
                packet["contract"]["scope"]["files"] = [name for name in expected if name != added]
                violations, _ = deterministic_evidence_checks(packet, strict=True)
                self.assertEqual([item["code"] for item in violations], ["out_of_scope_files"])
            self.assertEqual(snapshots[0], snapshots[1])
            # Only hash seed varies in this focused cross-process comparison.
            program = "import json,sys; from pathlib import Path; from reviewworthy.git import capture_pr_diff,PR_DIFF_FIELDS; d=capture_pr_diff(Path(sys.argv[1]),'main','feature'); print(json.dumps({k:d[k] for k in PR_DIFF_FIELDS},sort_keys=True))"
            for seed in ("1", "17"):
                completed = subprocess.run([sys.executable, "-c", program, str(root)], env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(completed.stdout), snapshots[0])

    def test_unsupported_git_byte_names_and_noncanonical_names_fail_explicitly(self) -> None:
        for name in (b"bad-\xff.txt", b"back\\slash.txt", b"C:drive.txt"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._git(root, "init", "-q")
                self._git(root, "config", "user.email", "test@example.invalid")
                self._git(root, "config", "user.name", "Reviewworthy Test")
                self._git(root, "branch", "-M", "main")
                self._git(root, "commit", "--allow-empty", "-qm", "base")
                self._git(root, "checkout", "-qb", "feature")
                # macOS rejects non-UTF8 worktree names; create a real Git
                # tree entry through the index so the immutable Diff can test it.
                blob = subprocess.run(["git", "-C", str(root), "hash-object", "-w", "--stdin"], input=b"content\n", capture_output=True, check=True).stdout.strip()
                subprocess.run(["git", "-C", str(root), "update-index", "-z", "--index-info"], input=b"100644 " + blob + b"\t" + name + b"\0", capture_output=True, check=True)
                self._git(root, "commit", "-qm", "unsupported path")
                with self.assertRaisesRegex(GitError, "UTF-8|canonical repository-relative"):
                    capture_pr_diff(root, "main", "feature")
