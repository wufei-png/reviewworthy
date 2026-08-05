"""Repository contribution-policy discovery and normalization.

Human-facing repository documents are the semantic authority. The optional
TOML file is a structured supplement and is never allowed to silently hide a
contradiction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Any, Iterable

from .util import relative_path


CLAIM_KEYS = (
    "ai_assistance",
    "issue_required",
    "disclosure_required",
    "disclosure_locations",
    "disclosure_stages",
    "human_pr_narrative_required",
    "security_private_reporting",
    "draft_pr_required",
    "discovery_evidence_allowed",
    "good_first_issue_ai_allowed",
)


@dataclass(frozen=True)
class PolicySource:
    path: str
    kind: str
    claims: dict[str, Any]
    error: str | None = None


def _claim(claims: dict[str, list[dict[str, Any]]], key: str, value: Any, path: Path, root: Path) -> None:
    claims.setdefault(key, []).append({"value": value, "source": relative_path(path, root)})


def _first_match(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in patterns)


def _claims_from_document(text: str, path: Path, root: Path) -> dict[str, Any]:
    lowered = text.lower()
    claims: dict[str, Any] = {}

    if _first_match(
        lowered,
        (
            r"\bai\b[^.!?\n]{0,80}(?:not allowed|prohibited|forbidden|must not|do not use|禁止|不得|不允许)",
            r"(?:do not|don't|must not|禁止|不得|不允许)[^.!?\n]{0,80}\bai\b",
        ),
    ):
        claims["ai_assistance"] = "prohibited"
    elif _first_match(lowered, (r"\bai\b[^.!?\n]{0,80}(?:allowed|permitted|welcome)",)):
        claims["ai_assistance"] = "allowed"

    if _first_match(
        lowered,
        (
            r"(?:issue|bug report)[^.!?\n]{0,50}(?:is )?(?:required|must come first)",
            r"(?:open|file|create)\s+(?:an?\s+)?issue[^.!?\n]{0,50}(?:before|first|prior)",
        ),
    ):
        claims["issue_required"] = True

    if _first_match(
        lowered,
        (
            r"(?:must|should|required|please)[^.!?\n]{0,50}(?:disclos|declare|mention)[^.!?\n]{0,50}(?:\bai\b|artificial intelligence)",
            r"(?:disclos|declare|mention)[^.!?\n]{0,50}(?:\bai\b|artificial intelligence)[^.!?\n]{0,50}(?:required|must)",
            r"(?:\bai\b|artificial intelligence)[^.!?\n]{0,50}(?:must|should|required)[^.!?\n]{0,50}(?:disclos|declare|mention)",
        ),
    ):
        claims["disclosure_required"] = True

        locations: list[str] = []
        if _first_match(lowered, (r"(?:disclos|declare|mention)[^.!?\n]{0,120}(?:pr|pull request)[^.!?\n]{0,50}(?:body|description)",)):
            locations.append("pr_body")
        if _first_match(lowered, (r"(?:disclos|declare|mention)[^.!?\n]{0,120}(?:commit[ -]+message|commit(?![ -]+trailer))",)):
            locations.append("commit_message")
        if _first_match(lowered, (r"(?:disclos|declare|mention)[^.!?\n]{0,120}commit[- ]trailer",)):
            locations.append("commit_trailer")
        if locations:
            claims["disclosure_locations"] = sorted(set(locations))

    if _first_match(
        lowered,
        (
            r"(?:pr|pull request)[^.!?\n]{0,100}(?:own words|your own|human[- ]written)",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,100}(?:must not|cannot|should not)[^.!?\n]{0,50}(?:pr|pull request|description)",
        ),
    ):
        claims["human_pr_narrative_required"] = True

    if _first_match(
        lowered,
        (
            r"security[^.!?\n]{0,100}(?:private|email|do not (?:open|file)[^.!?\n]{0,30}(?:public|issue))",
            r"(?:private|email)[^.!?\n]{0,60}security report",
        ),
    ):
        claims["security_private_reporting"] = True

    if _first_match(lowered, (r"(?:draft|work in progress)[^.!?\n]{0,80}(?:pr|pull request)[^.!?\n]{0,60}(?:required|must)",)):
        claims["draft_pr_required"] = True

    if _first_match(
        lowered,
        (
            r"discovery[^.!?\n]{0,100}(?:evidence|reproduction)[^.!?\n]{0,100}(?:sufficient|enough|allowed)",
            r"reproducible[^.!?\n]{0,100}(?:defect|failure)[^.!?\n]{0,100}(?:may|can)[^.!?\n]{0,50}(?:pr|contribution)",
        ),
    ):
        claims["discovery_evidence_allowed"] = True

    if _first_match(
        lowered,
        (
            r"good[- ]first[- ]issue[^.!?\n]{0,120}(?:ai|artificial intelligence)[^.!?\n]{0,60}(?:not allowed|prohibited|forbidden|must not)",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,120}good[- ]first[- ]issue[^.!?\n]{0,60}(?:not allowed|prohibited|forbidden|must not)",
        ),
    ):
        claims["good_first_issue_ai_allowed"] = False
    elif _first_match(
        lowered,
        (
            r"good[- ]first[- ]issue[^.!?\n]{0,120}(?:ai|artificial intelligence)[^.!?\n]{0,60}(?:allowed|permitted)",
        ),
    ):
        claims["good_first_issue_ai_allowed"] = True

    return claims


def _candidate_document_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for name in ("README.md", "README", "CONTRIBUTING.md", "CONTRIBUTING", "AGENTS.md", "SECURITY.md"):
        path = root / name
        if path.is_file():
            candidates.append(path)

    github_dir = root / ".github"
    if github_dir.is_dir():
        candidates.extend(
            path
            for path in github_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt", ".yml", ".yaml"}
            and ".github/workflows/" not in path.as_posix()
        )

    docs_dir = root / "docs"
    if docs_dir.is_dir():
        candidates.extend(
            path
            for path in docs_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".md", ".markdown"}
            and "docs/adr/" not in path.as_posix()
        )

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return sorted(unique)


def _nested(data: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = data
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if current is not None:
            return current
    return None


def _structured_claims(data: dict[str, Any]) -> dict[str, Any]:
    claims: dict[str, Any] = {}
    ai = _nested(data, ("ai",), ("contribution", "ai"))
    if isinstance(ai, dict):
        allowed = _nested(ai, ("allowed",), ("assistance_allowed",))
        if isinstance(allowed, bool):
            claims["ai_assistance"] = "allowed" if allowed else "prohibited"
        elif isinstance(allowed, str) and allowed in {"allowed", "prohibited", "unknown"}:
            claims["ai_assistance"] = allowed

        for key, claim_key in (("disclosure_locations", "disclosure_locations"), ("disclosure_stages", "disclosure_stages")):
            value = _nested(ai, (key,), ("disclosure", key.removeprefix("disclosure_")))
            if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
                claims[claim_key] = sorted(set(value))

    mappings: dict[str, tuple[tuple[str, ...], ...]] = {
        "issue_required": (("contribution", "issue_required"), ("issue_required",)),
        "disclosure_required": (("ai", "disclosure_required"), ("disclosure_required",)),
        "human_pr_narrative_required": (("pr", "human_narrative_required"), ("human_pr_narrative_required",)),
        "security_private_reporting": (("security", "private_reporting_required"), ("security_private_reporting",)),
        "draft_pr_required": (("pr", "draft_required"), ("draft_pr_required",)),
        "discovery_evidence_allowed": (("contribution", "discovery_evidence_allowed"), ("discovery_evidence_allowed",)),
        "good_first_issue_ai_allowed": (("contribution", "good_first_issue_ai_allowed"), ("good_first_issue_ai_allowed",)),
    }
    for key, paths in mappings.items():
        value = _nested(data, *paths)
        if isinstance(value, bool):
            claims[key] = value
    return claims


def inspect_policy(root: Path) -> dict[str, Any]:
    root = root.resolve()
    document_sources: list[PolicySource] = []
    document_claims: dict[str, list[dict[str, Any]]] = {}
    for path in _candidate_document_paths(root):
        try:
            text = path.read_text(encoding="utf-8")
            claims = _claims_from_document(text, path, root)
            document_sources.append(PolicySource(relative_path(path, root), "repository_document", claims))
            for key, value in claims.items():
                _claim(document_claims, key, value, path, root)
        except OSError as exc:
            document_sources.append(PolicySource(relative_path(path, root), "repository_document", {}, str(exc)))

    structured_path = root / ".reviewworthy" / "policy.toml"
    structured_claims: dict[str, Any] = {}
    structured_error: str | None = None
    if structured_path.is_file():
        try:
            with structured_path.open("rb") as handle:
                structured_claims = _structured_claims(tomllib.load(handle))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            structured_error = str(exc)

    conflicts: list[dict[str, Any]] = []
    for key, values in document_claims.items():
        unique = {str(item["value"]) for item in values}
        if len(unique) > 1:
            conflicts.append({"key": key, "kind": "repository_documents", "sources": values})
        if key in structured_claims and any(item["value"] != structured_claims[key] for item in values):
            conflicts.append(
                {
                    "key": key,
                    "kind": "document_vs_structured_policy",
                    "sources": values,
                    "structured_value": structured_claims[key],
                    "structured_source": ".reviewworthy/policy.toml",
                }
            )

    authoritative: dict[str, Any] = {}
    unknown: list[str] = []
    for key in CLAIM_KEYS:
        values = {str(item["value"]): item["value"] for item in document_claims.get(key, [])}
        if len(values) == 1:
            value = next(iter(values.values()))
            if value == "unknown":
                authoritative[key] = None
                unknown.append(key)
            else:
                authoritative[key] = value
        elif len(values) > 1:
            authoritative[key] = None
            unknown.append(key)
        elif key in structured_claims:
            value = structured_claims[key]
            if value == "unknown":
                authoritative[key] = None
                unknown.append(key)
            else:
                authoritative[key] = value
        else:
            authoritative[key] = None
            unknown.append(key)

    if structured_error:
        conflicts.append(
            {
                "key": "policy.toml",
                "kind": "invalid_structured_policy",
                "error": structured_error,
            }
        )

    posture = "conservative" if unknown or conflicts else "explicit"
    disclosure_locations = authoritative.get("disclosure_locations")
    if not isinstance(disclosure_locations, list) or not disclosure_locations:
        disclosure_locations = ["pr_body"] if authoritative.get("disclosure_required") is True or posture == "conservative" else []
    disclosure_stages = authoritative.get("disclosure_stages")
    if not isinstance(disclosure_stages, list):
        disclosure_stages = []

    return {
        "repository": str(root),
        "sources": [source.__dict__ for source in document_sources]
        + ([{"path": ".reviewworthy/policy.toml", "kind": "structured_policy", "claims": structured_claims, "error": structured_error}] if structured_path.exists() else []),
        "authoritative_claims": authoritative,
        "structured_claims": structured_claims,
        "unknown_claims": sorted(set(unknown)),
        "conflicts": conflicts,
        "hard_stops": [{"code": "policy_conflict", "reason": "Policy sources contradict each other."}] if conflicts else [],
        "posture": posture,
        "disclosure": {
            "required": authoritative.get("disclosure_required") is True or posture == "conservative",
            "locations": disclosure_locations,
            "stages": disclosure_stages,
        },
        "result": "blocked" if conflicts else "passed",
    }
