"""Explicit, idempotent GitHub writes through the user's authenticated gh CLI."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
from subprocess import CompletedProcess, run
from typing import Any, Callable
from urllib.parse import urlparse

from .evidence import append_evidence_summary, build_evidence_summary
from .git import PR_DIFF_FIELDS
from .repository import canonical_repository_slug, parse_public_record, repository_slugs_match
from .util import canonical_json, has_normalized_label, normalize_label, utc_now


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
    comparison: str | None = None
    base_tip_sha: str | None = None
    merge_base_sha: str | None = None
    head_sha: str | None = None
    subject_digest: str | None = None
    fingerprint_algorithm: str | None = None
    draft: bool = False
    purpose: str = "contribution"
    subject_id: str = ""
    issue_url: str | None = None
    link_note_template: str | None = None
    repository_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
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
            "purpose": self.purpose,
            "subject_id": self.subject_id,
            "issue_url": self.issue_url,
            "link_note_template": self.link_note_template,
            "repository_id": self.repository_id,
        }
        if self.kind == "pull_request":
            payload.update({
                "comparison": self.comparison,
                "base_tip_sha": self.base_tip_sha,
                "merge_base_sha": self.merge_base_sha,
                "head_sha": self.head_sha,
                "subject_digest": self.subject_digest,
                "fingerprint_algorithm": self.fingerprint_algorithm,
            })
        else:
            payload.update({"subject_digest": None})
        return payload


def build_operation(
    packet: dict[str, Any],
    repo: str,
    kind: str,
    title: str,
    body: str,
    base: str | None = None,
    head: str | None = None,
    diff: dict[str, Any] | None = None,
) -> RemoteOperation:
    if kind not in {"issue", "pull_request"}:
        raise ValueError("kind must be issue or pull_request")
    if kind == "pull_request" and not head:
        raise ValueError("head is required for a pull_request")
    if kind == "pull_request" and (
        not isinstance(diff, dict)
        or any(field not in diff for field in PR_DIFF_FIELDS)
        or diff.get("comparison") != "merge_base"
    ):
        raise ValueError("a complete merge-base PR Diff is required for a pull_request")
    canonical_repo = canonical_repository_slug(repo)
    issue_url = None
    basis = packet.get("basis")
    if isinstance(basis, dict):
        if basis.get("kind") == "issue":
            references = basis.get("references", [])
            if isinstance(references, list):
                issue_url = next((str(item) for item in references if parse_public_record(item or "") and parse_public_record(item or "").get("record_type") == "issue"), None)
        signal = basis.get("signal")
        if issue_url is None and isinstance(signal, dict) and signal.get("record_type") == "issue":
            parsed = parse_public_record(str(signal.get("reference", "")))
            if parsed and parsed.get("record_type") == "issue":
                issue_url = parsed["url"]
    link_note_template = "{pr_url}" if kind == "pull_request" and issue_url else None
    operation_body = body
    if kind == "pull_request":
        operation_body = append_evidence_summary(body, build_evidence_summary(packet, diff))
    payload: dict[str, Any] = {
        "purpose": "contribution",
        "subject_id": str(packet.get("contribution_id", "")),
        "contribution_id": packet.get("contribution_id"),
        "repo": canonical_repo,
        "kind": kind,
        "title": title,
        "body": operation_body,
        "base": base,
        "head": head,
        "draft": kind == "pull_request" and bool(
            isinstance(packet.get("policy"), dict)
            and isinstance(packet["policy"].get("authoritative_claims"), dict)
            and packet["policy"]["authoritative_claims"].get("draft_pr_required") is True
        ),
        "issue_url": issue_url,
        "link_note_template": link_note_template,
        "repository_id": packet.get("repository", {}).get("repository_id") if isinstance(packet.get("repository"), dict) else None,
    }
    if kind == "pull_request":
        payload.update({
            "comparison": diff.get("comparison"),
            "base_tip_sha": diff.get("base_tip_sha"),
            "merge_base_sha": diff.get("merge_base_sha"),
            "head_sha": diff.get("head_sha"),
            "subject_digest": diff.get("subject_digest"),
            "fingerprint_algorithm": diff.get("fingerprint_algorithm"),
        })
    else:
        payload.update({"subject_digest": None})
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:20]
    operation_id = f"rw-{digest}"
    marker = f"<!-- reviewworthy:v0.3:operation-id={operation_id} -->"
    marked_body = operation_body.rstrip() + f"\n\n{marker}"
    if kind == "issue":
        permissions = ("issues:write",)
    elif issue_url:
        permissions = ("contents:read", "pull-requests:write", "issues:write")
    else:
        permissions = ("contents:read", "pull-requests:write")
    return RemoteOperation(
        operation_id=operation_id,
        marker=marker,
        kind=kind,
        repo=canonical_repo,
        title=title,
        body=marked_body,
        permissions=permissions,
        base=base,
        head=head,
        comparison=payload.get("comparison"),
        base_tip_sha=payload.get("base_tip_sha"),
        merge_base_sha=payload.get("merge_base_sha"),
        head_sha=payload.get("head_sha"),
        subject_digest=payload.get("subject_digest"),
        fingerprint_algorithm=payload.get("fingerprint_algorithm"),
        draft=payload["draft"],
        purpose=payload["purpose"],
        subject_id=payload["subject_id"],
        issue_url=issue_url,
        link_note_template=link_note_template,
        repository_id=payload["repository_id"],
    )


def build_signal_operation(
    signal: dict[str, Any],
    repo: str,
    title: str,
    body: str,
) -> RemoteOperation:
    """Build an explicit Issue publication operation for a Contribution Signal."""

    record_type = signal.get("record_type") if isinstance(signal, dict) else None
    claim_type = signal.get("claim_type") if isinstance(signal, dict) else None
    reference = signal.get("reference") if isinstance(signal, dict) else None
    if record_type != "issue" or claim_type not in {"bug_report", "maintainer_request", "accepted_proposal", "reproducible_evidence"}:
        raise ValueError("Only Signal 0.3 issue records can be published as an Issue")
    if not isinstance(reference, str):
        raise ValueError("signal.reference must be a string")
    canonical_repo = canonical_repository_slug(repo)
    subject_id = signal.get("publication_subject_id") or f"{record_type}:{claim_type}:{reference}"
    payload = {
        "purpose": "signal_publication",
        "subject_id": subject_id,
        "signal_record_type": record_type,
        "signal_claim_type": claim_type,
        "signal_reference": subject_id,
        "repo": canonical_repo,
        "kind": "issue",
        "title": title,
        "body": body,
        "base": None,
        "head": None,
        "draft": False,
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:20]
    operation_id = f"rw-{digest}"
    marker = f"<!-- reviewworthy:v0.3:operation-id={operation_id} -->"
    marked_body = body.rstrip() + f"\n\n{marker}"
    return RemoteOperation(
        operation_id=operation_id,
        marker=marker,
        kind="issue",
        repo=canonical_repo,
        title=title,
        body=marked_body,
        permissions=("issues:write",),
        purpose=payload["purpose"],
        subject_id=payload["subject_id"],
    )


def operation_receipt_path(packet_path: Path, operation_id: str) -> Path:
    """Return ignored local state used to bridge GitHub read-after-write delay."""

    return packet_path.parent / "local" / "operations" / f"{operation_id}.json"


@contextmanager
def operation_lock(path: Path):
    """Claim one operation locally so concurrent invocations reconcile first."""

    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"operation_id": path.stem, "recorded_at": utc_now()}) + "\n")
    except FileExistsError as exc:
        raise GhError(f"Operation is already in progress; reconcile the lock before retrying: {lock_path}") from exc
    try:
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


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
    if operation.kind == "pull_request" and status in {"pr_created", "link_attempted", "linked", "needs_reconciliation"}:
        pr_url = receipt.get("pr_url")
        parsed_pr = parse_public_record(pr_url)
        if not parsed_pr or parsed_pr.get("record_type") != "pull_request" or not repository_slugs_match(f"{parsed_pr['owner']}/{parsed_pr['name']}", operation.repo):
            raise GhError(f"Pull-request receipt has no valid pr_url; reconcile before retrying: {path}")
        if operation.issue_url and receipt.get("issue_url") != operation.issue_url:
            raise GhError(f"Pull-request receipt has a mismatched issue_url; reconcile before retrying: {path}")
        if operation.issue_url and not parse_public_record(receipt.get("issue_url")):
            raise GhError(f"Pull-request receipt has an invalid issue_url; reconcile before retrying: {path}")
    elif status != "succeeded":
        raise GhError(f"Operation receipt has an unsupported status; reconcile before retrying: {path}")
    if status == "succeeded" and (not isinstance(receipt.get("remote"), str) or not receipt["remote"].strip()):
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
        "pr_url": "",
        "issue_url": operation.issue_url or "",
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


def _save_link_state(path: Path, operation: RemoteOperation, status: str, pr_url: str, *, reason: str = "") -> None:
    if operation.kind != "pull_request":
        raise GhError("Link receipt states apply only to pull-request operations")
    if not pr_url.strip():
        raise GhError("Pull-request link state needs a non-empty pr_url")
    record = {
        "operation_id": operation.operation_id,
        "marker": operation.marker,
        "repo": operation.repo,
        "kind": operation.kind,
        "operation": operation.as_dict(),
        "status": status,
        "pr_url": pr_url,
        "issue_url": operation.issue_url or "",
        "recorded_at": utc_now(),
    }
    if reason:
        record["reason"] = reason
    _write_operation_record(path, record, f"Could not persist {status} remote-write state")


def save_operation_pr_created(path: Path, operation: RemoteOperation, pr_url: str) -> None:
    _save_link_state(path, operation, "pr_created", pr_url)


def save_operation_link_attempted(path: Path, operation: RemoteOperation, pr_url: str) -> None:
    _save_link_state(path, operation, "link_attempted", pr_url)


def save_operation_linked(path: Path, operation: RemoteOperation, pr_url: str) -> None:
    _save_link_state(path, operation, "linked", pr_url)


def save_operation_needs_reconciliation(path: Path, operation: RemoteOperation, pr_url: str, reason: str) -> None:
    _save_link_state(path, operation, "needs_reconciliation", pr_url, reason=reason)


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

    def pull_request_head(self, pr_url: str) -> str:
        """Read the current head commit for one canonical GitHub pull request."""

        parsed = parse_public_record(pr_url)
        if not parsed or parsed.get("record_type") != "pull_request":
            raise GhError("Pull-request head lookup needs a canonical GitHub pull-request URL")
        record = self._json(
            [
                "api",
                f"repos/{parsed['owner']}/{parsed['name']}/pulls/{parsed['number']}",
                "--method",
                "GET",
            ]
        )
        head = record.get("head") if isinstance(record, dict) else None
        head_sha = head.get("sha") if isinstance(head, dict) else None
        if not isinstance(head_sha, str) or not head_sha.strip():
            raise GhError("GitHub pull-request response did not include head.sha")
        return head_sha.strip()

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

    def verify_public_reference(self, reference: str) -> dict[str, Any]:
        """Verify that a supported public GitHub record exists without inferring intent."""

        parsed = urlparse(reference)
        if parsed.scheme != "https" or parsed.netloc != "github.com":
            raise GhError("Signal reference must be an https://github.com public record")
        if parsed.query or parsed.fragment:
            raise GhError("Signal reference must not include a query string or fragment")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 4 or parts[2] not in {"issues", "pull", "discussions"} or not parts[3].isdigit():
            raise GhError("Signal reference must use /OWNER/REPO/issues|pull|discussions/NUMBER")
        owner, repository, record_type, number = parts[0], parts[1], parts[2], parts[3]
        repository_record = self._json(["api", f"repos/{owner}/{repository}", "--method", "GET"])
        if not isinstance(repository_record, dict):
            raise GhError("GitHub repository response was not an object")
        base_result = {
            "provider": "github",
            "host": "github.com",
            "reference": reference,
            "record_type": "pull_request" if record_type == "pull" else record_type[:-1] if record_type.endswith("s") else record_type,
            "repository": f"{owner}/{repository}",
            "repository_id": repository_record.get("id"),
            "number": int(number),
            "visibility": repository_record.get("visibility"),
        }
        if repository_record.get("visibility") != "public":
            return {**base_result, "verified": False, "error": "repository_not_public"}
        if record_type == "discussions":
            query = (
                "query($owner:String!,$name:String!,$number:Int!){"
                "repository(owner:$owner,name:$name){"
                "discussion(number:$number){number url title closed authorAssociation}}}"
            )
            response = self._json(
                [
                    "api", "graphql", "-f", f"query={query}",
                    "-F", f"owner={owner}", "-F", f"name={repository}", "-F", f"number={number}",
                ]
            )
            repository_data = response.get("data", {}).get("repository") if isinstance(response, dict) else None
            record = repository_data.get("discussion") if isinstance(repository_data, dict) else None
            if not isinstance(record, dict):
                raise GhError("GitHub Discussion GraphQL response did not include the requested discussion")
            canonical_url = record.get("url")
            normalized_record = {
                "html_url": canonical_url,
                "state": "closed" if record.get("closed") is True else "open",
                "author_association": record.get("authorAssociation"),
            }
            record = normalized_record
        else:
            api_type = "pulls" if record_type == "pull" else record_type
            endpoint = f"repos/{owner}/{repository}/{api_type}/{number}"
            record = self._json(["api", endpoint, "--method", "GET"])
        if not isinstance(record, dict):
            raise GhError("GitHub public-reference response was not an object")
        expected_url = f"https://github.com/{owner}/{repository}/{record_type}/{number}"
        canonical_url = record.get("html_url")
        if not isinstance(canonical_url, str) or not canonical_url.strip():
            return {**base_result, "verified": False, "error": "missing_canonical_url"}
        expected_parts = urlparse(expected_url)
        canonical_parts = urlparse(canonical_url)
        canonical_matches = (
            canonical_parts.scheme.lower() == expected_parts.scheme
            and canonical_parts.netloc.lower() == expected_parts.netloc
            and canonical_parts.path.rstrip("/").lower() == expected_parts.path.rstrip("/").lower()
        )
        if not canonical_matches:
            return {
                **base_result,
                "verified": False,
                "error": "reference_canonical_mismatch",
                "canonical_url": canonical_url,
            }
        result = {**base_result, "verified": True, "url": canonical_url, "state": record.get("state")}
        for key in ("state_reason", "locked", "author_association"):
            if key in record:
                result[key] = record[key]
        if isinstance(record.get("labels"), list):
            result["labels"] = [
                label.get("name")
                for label in record["labels"]
                if isinstance(label, dict) and isinstance(label.get("name"), str)
            ]
        return result

    def find_issue_link_note(self, issue_url: str, pr_url: str) -> list[dict[str, Any]]:
        """Find an exact one-line PR URL comment on the supporting Issue."""

        parsed_issue = parse_public_record(issue_url)
        if not parsed_issue or parsed_issue.get("record_type") != "issue":
            raise GhError("Issue link note needs a canonical GitHub Issue URL")
        if not parse_public_record(pr_url) or "/pull/" not in pr_url:
            raise GhError("Issue link note needs a canonical GitHub pull-request URL")
        pages = self._json(
            [
                "api",
                "--paginate",
                "--slurp",
                "--method",
                "GET",
                f"repos/{parsed_issue['owner']}/{parsed_issue['name']}/issues/{parsed_issue['number']}/comments",
                "-f",
                "per_page=100",
            ]
        )
        if not isinstance(pages, list):
            raise GhError("gh paginated Issue-comment response was not a list")
        matches: list[dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, list):
                raise GhError("gh paginated Issue-comment response contained a non-list page")
            for comment in page:
                if isinstance(comment, dict) and comment.get("body") == pr_url:
                    matches.append(comment)
        return matches

    def issue_commentability(self, issue_url: str) -> dict[str, Any]:
        """Check the read-side conditions needed before writing one Issue note."""

        try:
            remote = self.verify_public_reference(issue_url)
        except GhError as exc:
            return {"commentable": False, "reason": "issue_unavailable", "error": str(exc)}
        if not remote.get("verified"):
            return {"commentable": False, "reason": str(remote.get("error", "issue_unverified")), "remote": remote}
        if remote.get("record_type") != "issue":
            return {"commentable": False, "reason": "not_an_issue", "remote": remote}
        if remote.get("locked") is True:
            return {"commentable": False, "reason": "issue_locked", "remote": remote}
        state_reason = normalize_label(remote.get("state_reason", ""))
        if state_reason == "not planned":
            return {"commentable": False, "reason": "issue_not_planned", "remote": remote}
        if has_normalized_label(remote.get("labels"), "duplicate"):
            return {"commentable": False, "reason": "issue_duplicate", "remote": remote}
        return {"commentable": True, "remote": remote}

    def add_issue_note(self, issue_url: str, pr_url: str) -> dict[str, Any]:
        """Write the single canonical PR URL note to the supporting Issue."""

        parsed_issue = parse_public_record(issue_url)
        if not parsed_issue or parsed_issue.get("record_type") != "issue":
            raise GhError("Issue link note needs a canonical GitHub Issue URL")
        parsed_pr = parse_public_record(pr_url)
        if not parsed_pr or parsed_pr.get("record_type") != "pull_request":
            raise GhError("Issue link note needs a canonical GitHub pull-request URL")
        comment = self._json(
            [
                "api",
                f"repos/{parsed_issue['owner']}/{parsed_issue['name']}/issues/{parsed_issue['number']}/comments",
                "--method",
                "POST",
                "-f",
                f"body={pr_url}",
            ]
        )
        if not isinstance(comment, dict):
            raise GhError("GitHub Issue note response was not an object")
        return comment

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
