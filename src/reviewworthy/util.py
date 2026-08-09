"""Small standard-library helpers shared by the CLI and validators."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class CommandTimeoutError(RuntimeError):
    """A subprocess exceeded its explicit wall-clock bound."""


class CommandOutputLimitError(RuntimeError):
    """A subprocess exceeded its explicit captured-output bound."""


def run_bounded(
    argv: list[str],
    *,
    cwd: Path | str | None = None,
    timeout_seconds: float = 60,
    max_capture_bytes: int = 4 * 1024 * 1024,
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    """Run without unbounded in-memory capture; fail closed on time or size."""

    if timeout_seconds <= 0 or max_capture_bytes <= 0:
        raise ValueError("subprocess bounds must be positive")
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=os.name == "posix",
            )
        except OSError:
            raise

        def terminate() -> None:
            if process.poll() is not None:
                return
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()

        deadline = time.monotonic() + timeout_seconds
        while process.poll() is None:
            if stdout_file.tell() > max_capture_bytes or stderr_file.tell() > max_capture_bytes:
                terminate()
                raise CommandOutputLimitError(
                    f"Command output exceeded {max_capture_bytes} captured bytes: {argv[0]}"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate()
                raise CommandTimeoutError(f"Command timed out after {timeout_seconds:g}s: {argv[0]}")
            time.sleep(min(0.02, remaining))
        returncode = process.returncode

        def captured(handle: Any, name: str) -> bytes:
            size = handle.tell()
            handle.seek(0)
            value = handle.read(max_capture_bytes + 1)
            if size > max_capture_bytes or len(value) > max_capture_bytes:
                raise CommandOutputLimitError(
                    f"Command {name} exceeded {max_capture_bytes} captured bytes: {argv[0]}"
                )
            return bytes(value)

        stdout = captured(stdout_file, "stdout")
        stderr = captured(stderr_file, "stderr")
    if text:
        return subprocess.CompletedProcess(
            argv,
            returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def atomic_write_text(path: Path, value: str) -> None:
    """Replace one artifact atomically within its destination directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        if os.name == "posix":
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_json(path: Path, value: Any, *, sort_keys: bool = True) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def normalize_label(value: Any) -> str:
    """Normalize GitHub state reasons and labels for exact policy checks."""

    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def has_normalized_label(labels: Any, expected: str) -> bool:
    if not isinstance(labels, list):
        return False
    target = normalize_label(expected)
    for label in labels:
        value = label.get("name") if isinstance(label, dict) else label
        if normalize_label(value) == target:
            return True
    return False
