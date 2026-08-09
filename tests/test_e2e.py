from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from reviewworthy.action import check_evidence
from reviewworthy.cli import main
from reviewworthy.git import capture_pr_diff, local_state_path
from reviewworthy.github import build_operation
from reviewworthy.packet import semantic_snapshot

from helpers import valid_packet


class PrivatePacketPublicSummaryE2ETests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    def test_private_packet_drives_public_summary_and_action_without_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            root.mkdir()
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            self._git(root, "branch", "-M", "main")
            (root / "example.py").write_text("one\n", encoding="utf-8")
            self._git(root, "add", "example.py")
            self._git(root, "commit", "-qm", "base")
            self._git(root, "checkout", "-qb", "feature")
            (root / "example.py").write_text("one\ntwo\n", encoding="utf-8")
            self._git(root, "commit", "-qam", "feature")
            diff = capture_pr_diff(root, "main", "feature")

            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "packet", "init", "--root", str(root), "--contribution-id", "contribution-001",
                    "--repository", "example/project", "--json",
                ]), 0)
            packet_path = local_state_path(
                root, "reviewworthy/v0.3/contributions/contribution-001/packet.json"
            )
            self.assertIn("/.git/reviewworthy/v0.3/", packet_path.as_posix())

            packet = valid_packet()
            packet["diff"] = dict(diff)
            packet["verification"]["receipts"][0].update({
                "subject_digest": diff["subject_digest"],
                "head_sha": diff["head_sha"],
                "head_sha_before": diff["head_sha"],
                "head_sha_after": diff["head_sha"],
            })
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")

            operation = build_operation(
                packet, "example/project", "pull_request", packet["narrative"]["title"],
                packet["narrative"]["body"], "main", "feature", diff,
            )
            self.assertIn("reviewworthy:evidence-summary:start", operation.body)
            self.assertNotIn('"contract"', operation.body)
            result = check_evidence(
                operation.body,
                root=root,
                event_name="pull_request",
                event_repository="example/project",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )

            self.assertEqual(result["conclusion"], "success", result["violations"])
