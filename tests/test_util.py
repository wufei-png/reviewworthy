from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import unittest

from reviewworthy.util import CommandOutputLimitError, CommandTimeoutError, atomic_write_text, run_bounded


class UtilityBoundaryTests(unittest.TestCase):
    def test_bounded_runner_rejects_excess_output(self) -> None:
        with self.assertRaises(CommandOutputLimitError):
            run_bounded(
                [sys.executable, "-c", "print('x' * 1024)"],
                timeout_seconds=5,
                max_capture_bytes=32,
            )

    def test_bounded_runner_terminates_timeout(self) -> None:
        with self.assertRaises(CommandTimeoutError):
            run_bounded(
                [sys.executable, "-c", "import time; time.sleep(1)"],
                timeout_seconds=0.01,
                max_capture_bytes=32,
            )

    def test_atomic_writer_replaces_complete_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            atomic_write_text(path, "first\n")
            atomic_write_text(path, "second\n")

            self.assertEqual(path.read_text(), "second\n")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    @unittest.skipUnless(sys.platform != "win32", "directory fsync is a POSIX durability boundary")
    def test_atomic_writer_syncs_file_and_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            real_fsync = os.fsync
            descriptors: list[int] = []

            def record_fsync(descriptor: int) -> None:
                descriptors.append(descriptor)
                real_fsync(descriptor)

            with patch("reviewworthy.util.os.fsync", side_effect=record_fsync):
                atomic_write_text(path, "durable\n")

            self.assertEqual(len(descriptors), 2)
