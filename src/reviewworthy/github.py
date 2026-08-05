"""Explicit, idempotent GitHub writes through the user's authenticated gh CLI."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from subprocess import CompletedProcess, run
from typing import Any, Callable

from .util import canonical_json, utc_now


class GhError(RuntimeError):
    """The gh CLI could not complete a requested operation."""


@dataclass(frozen=True)
class RemoteOperation:
    operation_id: str
    marker: str
    kind: str
    repo: str
    title: str
    body: str
    permissions: tuple[str, ...]
    base: str | None = None
    head: str | None = None
    draft: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "marker": self.marker,
            "kind": self.kind,
            "repo": self.repo,
            "title": self.title,
            "body": self.body,
            "permissions": list(self.permissions),
            "base": self.base,
            "head": self.head,
            "draft": self.draft,
        }


def build_operation(
    packet: dict[str, Any],
    repo: str,
    kind: str,
    title: str,
    body: str,
    base: str | None = None,
    head: str | None = None,
) -> RemoteOperation:
    if kind not in {"issue", "pull_request"}:
        raise ValueError("kind must be issue or pull_request")
    if kind == "pull_request" and not head:
        raise ValueError("head is required for a pull_request")
    payload = {
        "contribution_id": packet.get("contribution_id"),
        "repo": repo,
        "kind": kind,
        "title": title,
        "body": body,
        "base": base,
        "head": head,
        "draft": kind == "pull_request" and bool(
            isinstance(packet.get("policy"), dict)
            and isinstance(packet["policy"].get("authoritative_claims"), dict)
            and packet["policy"]["authoritative_claims"].get("draft_pr_required") is True
        ),
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:20]
    operation_id = f"rw-{digest}"
    marker = f"<!-- reviewworthy:operation-id={operation_id} -->"
    marked_body = body.rstrip() + f"\n\n{marker}"
    permissions = ("issues:write",) if kind == "issue" else ("contents:read", "pull-requests:write")
    return RemoteOperation(operation_id, marker, kind, repo, title, marked_body, permissions, base, head, payload["draft"])


def operation_receipt_path(packet_path: Path, operation_id: str) -> Path:
    """Return ignored local state used to bridge GitHub read-after-write delay."""

    return packet_path.parent / "local" / "operations" / f"{operation_id}.json"


def load_operation_receipt(path: Path, operation: RemoteOperation) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GhError(f"Operation receipt is unreadable; reconcile before retrying: {path}: {exc}") from exc
    if not isinstance(receipt, dict) or any(
        receipt.get(key) != expected
        for key, expected in {
            "operation_id": operation.operation_id,
            "marker": operation.marker,
            "repo": operation.repo,
            "kind": operation.kind,
        }.items()
    ):
        raise GhError(f"Operation receipt does not match the rendered operation; reconcile before retrying: {path}")
    if receipt.get("operation") != operation.as_dict():
        raise GhError(f"Operation receipt payload does not match the rendered operation; reconcile before retrying: {path}")
    status = receipt.get("status")
    if status == "pending":
        raise GhError(f"Operation has an uncertain or pending remote write; reconcile before retrying: {path}")
    if status != "succeeded":
        raise GhError(f"Operation receipt has an unsupported status; reconcile before retrying: {path}")
    if not isinstance(receipt.get("remote"), str) or not receipt["remote"].strip():
        raise GhError(f"Operation receipt has no valid remote result; reconcile before retrying: {path}")
    if not isinstance(receipt.get("recorded_at"), str) or not receipt["recorded_at"].strip():
        raise GhError(f"Operation receipt has no valid timestamp; reconcile before retrying: {path}")
    return receipt


def _write_operation_record(path: Path, record: dict[str, Any], failure_message: str) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_path, path)
    except OSError as exc:
        raise GhError(f"{failure_message}: {path}: {exc}") from exc


def save_operation_pending(path: Path, operation: RemoteOperation) -> None:
    record = {
        "operation_id": operation.operation_id,
        "marker": operation.marker,
        "repo": operation.repo,
        "kind": operation.kind,
        "operation": operation.as_dict(),
        "status": "pending",
        "recorded_at": utc_now(),
    }
    _write_operation_record(path, record, "Could not persist pending remote-write state")


def save_operation_receipt(path: Path, operation: RemoteOperation, remote: str) -> None:
    if not isinstance(remote, str) or not remote.strip():
        raise GhError("Remote write returned an empty remote result; reconcile before retrying")
    receipt = {
        "operation_id": operation.operation_id,
        "marker": operation.marker,
        "repo": operation.repo,
        "kind": operation.kind,
        "operation": operation.as_dict(),
        "status": "succeeded",
        "remote": remote,
        "recorded_at": utc_now(),
    }
    _write_operation_record(path, receipt, "Remote write succeeded but operation receipt could not be saved; reconcile before retrying")


class GhClient:
    def __init__(self, runner: Callable[..., CompletedProcess[str]] = run):
        self._runner = runner

    def _invoke(self, args: list[str]) -> str:
        completed = self._runner(["gh", *args], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "gh command failed").strip()
            raise GhError(detail)
        return completed.stdout or ""

    def _json(self, args: list[str]) -> Any:
        output = self._invoke(args)
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise GhError(f"gh returned invalid JSON: {exc}") from exc

    def find_existing(self, operation: RemoteOperation) -> list[dict[str, Any]]:
        pages = self._json(
            [
                "api",
                "--paginate",
                "--slurp",
                "--method",
                "GET",
                f"repos/{operation.repo}/issues",
                "-f",
                "state=all",
                "-f",
                "per_page=100",
            ]
        )
        if not isinstance(pages, list):
            raise GhError("gh paginated issue response was not a list")
        items: list[dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, list):
                raise GhError("gh paginated issue response contained a non-list page")
            for item in page:
                if not isinstance(item, dict):
                    continue
                is_pr = "pull_request" in item
                if operation.kind == "pull_request" and not is_pr:
                    continue
                if operation.kind == "issue" and is_pr:
                    continue
                normalized = {
                    "number": item.get("number"),
                    "url": item.get("html_url") or item.get("url"),
                    "title": item.get("title"),
                    "body": item.get("body", ""),
                    "state": item.get("state"),
                }
                if operation.marker in str(normalized["body"]):
                    items.append(normalized)
        return items

    def search_candidates(self, repo: str, query: str, kind: str = "both") -> list[dict[str, Any]]:
        """Search Issues/PRs for duplicate-work evidence without mutating GitHub."""

        kinds = ("issue", "pr") if kind == "both" else (kind,)
        matches: list[dict[str, Any]] = []
        for current_kind in kinds:
            items = self._json(
                [
                    current_kind,
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "all",
                    "--search",
                    query,
                    "--limit",
                    "100",
                    "--json",
                    "number,url,title,body,state",
                ]
            )
            if not isinstance(items, list):
                raise GhError(f"gh {current_kind} search response was not a list")
            for item in items:
                if isinstance(item, dict):
                    matches.append({"kind": "pull_request" if current_kind == "pr" else "issue", **item})
        return matches

    def create(self, operation: RemoteOperation) -> str:
        if operation.kind == "issue":
            return self._invoke(
                ["issue", "create", "--repo", operation.repo, "--title", operation.title, "--body", operation.body]
            ).strip()
        args = [
            "pr",
            "create",
            "--repo",
            operation.repo,
            "--title",
            operation.title,
            "--body",
            operation.body,
            "--base",
            operation.base or "main",
            "--head",
            operation.head or "",
        ]
        if operation.draft:
            args.append("--draft")
        return self._invoke(args).strip()
