"""Canonical repository and public-record identity helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


GITHUB_HOST = "github.com"
_SLUG_RE = re.compile(r"^(?P<owner>[^/\s]+)/(?P<name>[^/\s]+)$")
_RECORD_RE = re.compile(r"^https://github\.com/(?P<owner>[^/\s]+)/(?P<name>[^/\s]+)/(?:issues|pull)/(?P<number>[1-9][0-9]*)$")


def parse_repository_slug(value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValueError("repository must be an owner/name string")
    match = _SLUG_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("repository must use the owner/name form")
    return match.group("owner"), match.group("name")


def repository_identity(
    value: str | dict[str, Any],
    *,
    repository_id: int | None = None,
    default_branch: str = "main",
    base_sha: str = "",
) -> dict[str, Any]:
    if isinstance(value, dict):
        provider = str(value.get("provider", "github"))
        host = str(value.get("host", GITHUB_HOST))
        owner = str(value.get("owner", "")).strip()
        name = str(value.get("name", "")).strip()
        if not owner or not name:
            raise ValueError("repository identity needs owner and name")
        try:
            owner, name = parse_repository_slug(f"{owner}/{name}")
        except ValueError as exc:
            raise ValueError("repository identity owner and name must use the owner/name form") from exc
        parsed_id = value.get("repository_id", repository_id)
        parsed_branch = str(value.get("default_branch", default_branch) or default_branch)
        parsed_base = str(value.get("base_sha", base_sha) or base_sha)
    else:
        owner, name = parse_repository_slug(value)
        provider = "github"
        host = GITHUB_HOST
        parsed_id = repository_id
        parsed_branch = default_branch
        parsed_base = base_sha
    if provider != "github" or host != GITHUB_HOST:
        raise ValueError("only the github.com provider is supported in packet identity 0.1")
    if parsed_id is not None and (not isinstance(parsed_id, int) or isinstance(parsed_id, bool) or parsed_id <= 0):
        raise ValueError("repository_id must be a positive integer when present")
    return {
        "provider": provider,
        "host": host,
        "owner": owner,
        "name": name,
        "repository_id": parsed_id,
        "default_branch": parsed_branch,
        "base_sha": parsed_base,
    }


def repository_slug(value: str | dict[str, Any]) -> str:
    identity = repository_identity(value)
    return f"{identity['owner']}/{identity['name']}"


def canonical_repository_slug(value: str | dict[str, Any]) -> str:
    identity = repository_identity(value)
    return f"{identity['owner'].casefold()}/{identity['name'].casefold()}"


def repository_matches(identity: Any, slug: str) -> bool:
    try:
        expected = repository_identity(identity)
        owner, name = parse_repository_slug(slug)
    except ValueError:
        return False
    return expected["owner"].casefold() == owner.casefold() and expected["name"].casefold() == name.casefold()


def repository_slugs_match(left: Any, right: Any) -> bool:
    """Compare two owner/name values using GitHub's case-insensitive identity."""

    try:
        left_owner, left_name = parse_repository_slug(left)
        right_owner, right_name = parse_repository_slug(right)
    except ValueError:
        return False
    return left_owner.casefold() == right_owner.casefold() and left_name.casefold() == right_name.casefold()


def parse_public_record(reference: str) -> dict[str, Any] | None:
    if not isinstance(reference, str):
        return None
    parsed = urlparse(reference.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != GITHUB_HOST or parsed.query or parsed.fragment:
        return None
    match = _RECORD_RE.fullmatch(reference.strip())
    if not match:
        return None
    path_parts = [part for part in parsed.path.split("/") if part]
    record_type = path_parts[2]
    return {
        "provider": "github",
        "host": GITHUB_HOST,
        "owner": match.group("owner"),
        "name": match.group("name"),
        "record_type": "pull_request" if record_type == "pull" else "issue",
        "number": int(match.group("number")),
        "url": reference.strip(),
    }


def validate_repository_identity(value: Any, path: str = "repository") -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return [{"code": "invalid_repository_identity", "message": "repository must be an object", "path": path}]
    for key in ("provider", "host", "owner", "name", "default_branch"):
        if not isinstance(value.get(key), str) or not value.get(key, "").strip():
            errors.append({"code": "invalid_repository_identity", "message": f"repository.{key} is required", "path": f"{path}.{key}"})
    if isinstance(value.get("owner"), str) and isinstance(value.get("name"), str) and value.get("owner", "").strip() and value.get("name", "").strip():
        try:
            parse_repository_slug(f"{value['owner']}/{value['name']}")
        except ValueError:
            errors.append({"code": "invalid_repository_identity", "message": "repository.owner and repository.name must use the owner/name form", "path": path})
    if value.get("provider") not in {None, "github"}:
        errors.append({"code": "unsupported_repository_provider", "message": "Only the github provider is supported", "path": f"{path}.provider"})
    if value.get("host") not in {None, GITHUB_HOST}:
        errors.append({"code": "unsupported_repository_host", "message": "Only github.com is supported", "path": f"{path}.host"})
    repository_id = value.get("repository_id")
    if repository_id is not None and (not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0):
        errors.append({"code": "invalid_repository_id", "message": "repository.repository_id must be a positive integer when present", "path": f"{path}.repository_id"})
    return errors
