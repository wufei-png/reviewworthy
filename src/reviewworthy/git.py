"""Read-only Git evidence capture and command verification."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Any

from .util import canonical_json, relative_path, utc_now


PR_DIFF_FIELDS = (
    "comparison",
    "base_tip_sha",
    "merge_base_sha",
    "head_sha",
    "subject_digest",
    "fingerprint_algorithm",
    "changed_files",
    "additions",
    "deletions",
)

FINGERPRINT_ALGORITHM = "git-raw-content-v1"


class GitError(RuntimeError):
    """A requested Git evidence operation could not be completed."""


def _run_git(root: Path, args: list[str], *, text: bool = True) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=text, check=False)
    except OSError as exc:
        raise GitError(f"Could not invoke git: {exc}") from exc


def resolve_ref(root: Path, ref: str) -> str:
    completed = _run_git(root.resolve(), ["rev-parse", "--verify", f"{ref}^{{commit}}"])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown git ref").strip()
        raise GitError(f"Could not resolve Git ref {ref!r}: {detail}")
    return str(completed.stdout).strip()


def current_head(root: Path) -> str:
    return resolve_ref(root, "HEAD")


def local_state_path(root: Path, relative: str) -> Path:
    """Resolve private Reviewworthy state inside Git metadata, never the worktree."""

    root = root.resolve()
    completed = _run_git(root, ["rev-parse", "--git-path", relative])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "not a Git worktree").strip()
        raise GitError(f"Could not resolve Git-private state: {detail}")
    value = Path(str(completed.stdout).strip())
    return value if value.is_absolute() else (root / value).resolve()


def _worktree_status(root: Path) -> list[str]:
    completed = _run_git(root.resolve(), ["status", "--porcelain=v1", "--untracked-files=all"])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git status failed").strip()
        raise GitError(detail)
    return [line for line in str(completed.stdout).splitlines() if line]


def _parse_numstat(output: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        if parts[0].isdigit():
            additions += int(parts[0])
        if parts[1].isdigit():
            deletions += int(parts[1])
    return additions, deletions


def _capture_diff_between(root: Path, start_sha: str, head_sha: str) -> dict[str, Any]:
    patch = _run_git(root, ["diff", "--binary", "--no-ext-diff", "--no-renames", start_sha, head_sha], text=False)
    if patch.returncode != 0:
        detail = (patch.stderr or patch.stdout or b"git diff failed").decode("utf-8", errors="replace").strip()
        raise GitError(detail)
    names = _run_git(root, ["diff", "--name-only", "--no-ext-diff", "--no-renames", start_sha, head_sha])
    if names.returncode != 0:
        raise GitError((names.stderr or names.stdout or "git diff --name-only failed").strip())
    numstat = _run_git(root, ["diff", "--numstat", "--no-ext-diff", "--no-renames", start_sha, head_sha])
    if numstat.returncode != 0:
        raise GitError((numstat.stderr or numstat.stdout or "git diff --numstat failed").strip())
    additions, deletions = _parse_numstat(str(numstat.stdout))
    patch_bytes = bytes(patch.stdout)
    raw = _run_git(
        root,
        ["diff", "--raw", "-z", "--no-abbrev", "--no-ext-diff", "--no-renames", start_sha, head_sha],
        text=False,
    )
    if raw.returncode != 0:
        detail = (raw.stderr or raw.stdout or b"git diff --raw failed").decode("utf-8", errors="replace").strip()
        raise GitError(detail)
    parts = bytes(raw.stdout).split(b"\0")
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(parts) and parts[index]:
        metadata = parts[index]
        if index + 1 >= len(parts) or not parts[index + 1]:
            raise GitError("git diff --raw returned an incomplete path record")
        fields = metadata.split()
        if len(fields) != 5 or not fields[0].startswith(b":"):
            raise GitError("git diff --raw returned an unsupported record")
        entries.append(
            {
                "old_mode": fields[0][1:].decode("ascii"),
                "new_mode": fields[1].decode("ascii"),
                "old_blob": fields[2].decode("ascii"),
                "new_blob": fields[3].decode("ascii"),
                "status": fields[4].decode("ascii"),
                "path_hex": parts[index + 1].hex(),
            }
        )
        index += 2
    entries.sort(key=lambda item: (item["path_hex"], item["status"]))
    subject_digest = sha256(canonical_json(entries).encode("utf-8")).hexdigest()
    return {
        "subject_digest": subject_digest,
        "fingerprint_algorithm": FINGERPRINT_ALGORITHM,
        "patch_sha256": sha256(patch_bytes).hexdigest(),
        "changed_files": sorted(line for line in str(names.stdout).splitlines() if line),
        "additions": additions,
        "deletions": deletions,
        "captured_at": utc_now(),
        "root": relative_path(root, root),
        "provenance": "cli_executed",
    }


def capture_pr_diff(root: Path, base: str, head: str) -> dict[str, Any]:
    """Capture the contribution introduced from the merge base to PR head."""

    root = root.resolve()
    base_tip_sha = resolve_ref(root, base)
    head_sha = resolve_ref(root, head)
    completed = _run_git(root, ["merge-base", base_tip_sha, head_sha])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git merge-base failed").strip()
        raise GitError(detail)
    merge_base_sha = str(completed.stdout).strip()
    if not merge_base_sha:
        raise GitError("git merge-base returned no commit")
    return {
        "comparison": "merge_base",
        "base_tip_sha": base_tip_sha,
        "merge_base_sha": merge_base_sha,
        "head_sha": head_sha,
        **_capture_diff_between(root, merge_base_sha, head_sha),
    }


def run_verification(root: Path, head: str, argv: list[str]) -> dict[str, Any]:
    root = root.resolve()
    if not argv:
        raise ValueError("verification command must not be empty")
    expected_head = resolve_ref(root, head)
    head_before = current_head(root)
    if head_before != expected_head:
        raise GitError(f"Working tree HEAD moved: expected {expected_head}, found {head_before}")
    if _worktree_status(root):
        raise GitError("Verification requires a clean worktree before execution")
    started_at = utc_now()
    try:
        completed = subprocess.run(argv, cwd=root, capture_output=True, text=False, check=False)
    except OSError as exc:
        raise GitError(f"Could not execute verification command: {exc}") from exc
    finished_at = utc_now()
    stdout = bytes(completed.stdout or b"")
    stderr = bytes(completed.stderr or b"")
    head_after = current_head(root)
    worktree_clean_after = not _worktree_status(root)
    valid = head_before == head_after and worktree_clean_after
    failure_reasons: list[str] = []
    if head_before != head_after:
        failure_reasons.append("head_changed_after_execution")
    if not worktree_clean_after:
        failure_reasons.append("worktree_dirty_after_execution")
    return {
        "argv": list(argv),
        "cwd": relative_path(root, root),
        "exit_code": completed.returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "head_sha": expected_head,
        "head_sha_before": head_before,
        "head_sha_after": head_after,
        "worktree_clean_before": True,
        "worktree_clean_after": worktree_clean_after,
        "status": "valid" if valid else "invalid",
        **({"failure_reason": ",".join(failure_reasons)} if failure_reasons else {}),
        "stdout_sha256": sha256(stdout).hexdigest(),
        "stderr_sha256": sha256(stderr).hexdigest(),
        "provenance": "cli_executed",
    }
