"""Repository contribution-policy discovery and normalization.

Human-facing repository documents are the semantic authority. The optional
TOML file is a structured supplement and is never allowed to silently hide a
contradiction.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import hashlib
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
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)


_DOCUMENT_PROVENANCE_PATTERNS = {
    "ai_assistance": (
        r"\bai\b[^.!?\n]{0,80}(?:not allowed|prohibited|forbidden|must not|do not use|allowed|permitted|welcome|禁止|不得|不允许)",
        r"(?:do not|don't|must not|禁止|不得|不允许)[^.!?\n]{0,80}\bai\b",
    ),
    "issue_required": (
        r"(?:issue|bug report)[^.!?\n]{0,50}(?:is )?(?:required|must come first)",
        r"(?:open|file|create)\s+(?:an?\s+)?issue[^.!?\n]{0,50}(?:before|first|prior)",
    ),
    "disclosure_required": (
        r"(?:must|should|required|please)[^.!?\n]{0,50}(?:disclos|declare|mention)[^.!?\n]{0,50}(?:\bai\b|artificial intelligence)",
        r"(?:disclos|declare|mention)[^.!?\n]{0,50}(?:\bai\b|artificial intelligence)[^.!?\n]{0,50}(?:required|must)",
        r"(?:\bai\b|artificial intelligence)[^.!?\n]{0,50}(?:must|should|required)[^.!?\n]{0,50}(?:disclos|declare|mention)",
    ),
    "disclosure_locations": (
        r"(?:disclos|declare|mention)[^.!?\n]{0,120}(?:pr|pull request)[^.!?\n]{0,50}(?:body|description)",
        r"(?:disclos|declare|mention)[^.!?\n]{0,120}(?:commit[ -]+message|commit(?![ -]+trailer))",
        r"(?:disclos|declare|mention)[^.!?\n]{0,120}commit[- ]trailer",
    ),
    "human_pr_narrative_required": (
        r"(?:pr|pull request)[^.!?\n]{0,100}(?:own words|your own|human[- ]written)",
        r"(?:ai|artificial intelligence)[^.!?\n]{0,100}(?:must not|cannot|should not)[^.!?\n]{0,50}(?:pr|pull request|description)",
    ),
    "security_private_reporting": (
        r"security[^.!?\n]{0,100}(?:private|email|do not (?:open|file)[^.!?\n]{0,30}(?:public|issue))",
        r"(?:private|email)[^.!?\n]{0,60}security report",
    ),
    "draft_pr_required": (r"(?:draft|work in progress)[^.!?\n]{0,80}(?:pr|pull request)[^.!?\n]{0,60}(?:required|must)",),
    "discovery_evidence_allowed": (
        r"discovery[^.!?\n]{0,100}(?:evidence|reproduction)[^.!?\n]{0,100}(?:sufficient|enough|allowed)",
        r"reproducible[^.!?\n]{0,100}(?:defect|failure)[^.!?\n]{0,100}(?:may|can)[^.!?\n]{0,50}(?:pr|contribution)",
    ),
    "good_first_issue_ai_allowed": (
        r"good[- ]first[- ]issue[^.!?\n]{0,120}(?:ai|artificial intelligence)[^.!?\n]{0,60}(?:not allowed|prohibited|forbidden|must not|allowed|permitted)",
        r"(?:ai|artificial intelligence)[^.!?\n]{0,120}good[- ]first[- ]issue[^.!?\n]{0,60}(?:not allowed|prohibited|forbidden|must not|allowed|permitted)",
    ),
}

_STRUCTURED_PROVENANCE_PATTERNS = {
    "ai_assistance": (r"^\s*(?:allowed|assistance_allowed)\s*=",),
    "issue_required": (r"^\s*issue_required\s*=",),
    "disclosure_required": (r"^\s*disclosure_required\s*=",),
    "disclosure_locations": (r"^\s*disclosure_locations\s*=",),
    "disclosure_stages": (r"^\s*disclosure_stages\s*=",),
    "human_pr_narrative_required": (r"^\s*human_narrative_required\s*=",),
    "security_private_reporting": (r"^\s*private_reporting_required\s*=",),
    "draft_pr_required": (r"^\s*draft_required\s*=",),
    "discovery_evidence_allowed": (r"^\s*discovery_evidence_allowed\s*=",),
    "good_first_issue_ai_allowed": (r"^\s*good_first_issue_ai_allowed\s*=",),
}


def _provenance(path: Path, root: Path, text: str, key: str, match: re.Match[str] | None = None) -> dict[str, Any]:
    lines = text.splitlines() or [""]
    patterns = _STRUCTURED_PROVENANCE_PATTERNS if path.name == "policy.toml" else _DOCUMENT_PROVENANCE_PATTERNS
    if match is None:
        match = next(
            (found for pattern in patterns.get(key, ()) if (found := re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL))),
            None,
        )
    if match:
        line_start = text.count("\n", 0, match.start()) + 1
        line_end = text.count("\n", 0, match.end()) + 1
        excerpt = "\n".join(lines[line_start - 1:line_end]).strip()
    else:
        line_start = line_end = 1
        excerpt = lines[0].strip()
    provenance = {
        "source": relative_path(path, root),
        "line_start": line_start,
        "line_end": line_end,
        "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
    }
    if match:
        provenance.update({"match_start": match.start(), "match_end": match.end()})
    return provenance


def _claim(
    claims: dict[str, list[dict[str, Any]]],
    key: str,
    value: Any,
    path: Path,
    root: Path,
    text: str,
    match: re.Match[str] | None = None,
) -> None:
    claims.setdefault(key, []).append({"value": value, **_provenance(path, root, text, key, match)})


def _first_match(text: str, patterns: Iterable[str]) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match
    return None


def _claims_from_document(text: str, path: Path, root: Path) -> tuple[dict[str, Any], dict[str, re.Match[str]]]:
    claims: dict[str, Any] = {}
    matches: dict[str, re.Match[str]] = {}

    def record(key: str, value: Any, match: re.Match[str] | None) -> None:
        claims[key] = value
        if match:
            matches[key] = match

    prohibited_ai_match = _first_match(
        text,
        (
            r"\bai\b[^.!?\n]{0,80}(?:not allowed|prohibited|forbidden|must not|do not use|禁止|不得|不允许)",
            r"(?:do not|don't|must not|禁止|不得|不允许)[^.!?\n]{0,80}\bai\b",
        ),
    )
    if prohibited_ai_match:
        record("ai_assistance", "prohibited", prohibited_ai_match)
    else:
        allowed_ai_match = _first_match(text, (r"\bai\b[^.!?\n]{0,80}(?:allowed|permitted|welcome)",))
        if allowed_ai_match:
            record("ai_assistance", "allowed", allowed_ai_match)

    issue_match = _first_match(
        text,
        (
            r"(?:issue|bug report)[^.!?\n]{0,50}(?:is )?(?:required|must come first)",
            r"(?:open|file|create)\s+(?:an?\s+)?issue[^.!?\n]{0,50}(?:before|first|prior)",
        ),
    )
    if issue_match:
        record("issue_required", True, issue_match)

    disclosure_match = _first_match(
        text,
        (
            r"(?:must|should|required|please)[^.!?\n]{0,50}(?:disclos|declare|mention)[^.!?\n]{0,50}(?:\bai\b|artificial intelligence)",
            r"(?:disclos|declare|mention)[^.!?\n]{0,50}(?:\bai\b|artificial intelligence)[^.!?\n]{0,50}(?:required|must)",
            r"(?:\bai\b|artificial intelligence)[^.!?\n]{0,50}(?:must|should|required)[^.!?\n]{0,50}(?:disclos|declare|mention)",
        ),
    )
    if disclosure_match:
        record("disclosure_required", True, disclosure_match)

        locations: list[str] = []
        location_matches: list[re.Match[str]] = []
        pr_body_match = _first_match(text, (r"(?:disclos|declare|mention)[^.!?\n]{0,120}(?:pr|pull request)[^.!?\n]{0,50}(?:body|description)",))
        if pr_body_match:
            locations.append("pr_body")
            location_matches.append(pr_body_match)
        commit_message_match = _first_match(text, (r"(?:disclos|declare|mention)[^.!?\n]{0,120}(?:commit[ -]+message|commit(?![ -]+trailer))",))
        if commit_message_match:
            locations.append("commit_message")
            location_matches.append(commit_message_match)
        commit_trailer_match = _first_match(text, (r"(?:disclos|declare|mention)[^.!?\n]{0,120}commit[- ]trailer",))
        if commit_trailer_match:
            locations.append("commit_trailer")
            location_matches.append(commit_trailer_match)
        if locations:
            record("disclosure_locations", sorted(set(locations)), location_matches[0] if location_matches else disclosure_match)

    human_narrative_match = _first_match(
        text,
        (
            r"(?:pr|pull request)[^.!?\n]{0,100}(?:own words|your own|human[- ]written)",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,100}(?:must not|cannot|should not)[^.!?\n]{0,50}(?:pr|pull request|description)",
        ),
    )
    if human_narrative_match:
        record("human_pr_narrative_required", True, human_narrative_match)

    security_match = _first_match(
        text,
        (
            r"security[^.!?\n]{0,100}(?:private|email|do not (?:open|file)[^.!?\n]{0,30}(?:public|issue))",
            r"(?:private|email)[^.!?\n]{0,60}security report",
        ),
    )
    if security_match:
        record("security_private_reporting", True, security_match)

    draft_match = _first_match(text, (r"(?:draft|work in progress)[^.!?\n]{0,80}(?:pr|pull request)[^.!?\n]{0,60}(?:required|must)",))
    if draft_match:
        record("draft_pr_required", True, draft_match)

    discovery_match = _first_match(
        text,
        (
            r"discovery[^.!?\n]{0,100}(?:evidence|reproduction)[^.!?\n]{0,100}(?:sufficient|enough|allowed)",
            r"reproducible[^.!?\n]{0,100}(?:defect|failure)[^.!?\n]{0,100}(?:may|can)[^.!?\n]{0,50}(?:pr|contribution)",
        ),
    )
    if discovery_match:
        record("discovery_evidence_allowed", True, discovery_match)

    prohibited_good_first_match = _first_match(
        text,
        (
            r"good[- ]first[- ]issue[^.!?\n]{0,120}(?:ai|artificial intelligence)[^.!?\n]{0,60}(?:not allowed|prohibited|forbidden|must not)",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,120}good[- ]first[- ]issue[^.!?\n]{0,60}(?:not allowed|prohibited|forbidden|must not)",
        ),
    )
    if prohibited_good_first_match:
        record("good_first_issue_ai_allowed", False, prohibited_good_first_match)
    else:
        allowed_good_first_match = _first_match(
            text,
        (
            r"good[- ]first[- ]issue[^.!?\n]{0,120}(?:ai|artificial intelligence)[^.!?\n]{0,60}(?:allowed|permitted)",
        ),
        )
        if allowed_good_first_match:
            record("good_first_issue_ai_allowed", True, allowed_good_first_match)

    return claims, matches


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
    value, _path = _nested_with_path(data, *paths)
    return value


def _nested_with_path(data: dict[str, Any], *paths: tuple[str, ...]) -> tuple[Any, tuple[str, ...] | None]:
    for path in paths:
        current: Any = data
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if current is not None:
            return current, path
    return None, None


def _structured_claims(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]]:
    claims: dict[str, Any] = {}
    claim_paths: dict[str, tuple[str, ...]] = {}

    def record(key: str, value: Any, path: tuple[str, ...] | None) -> None:
        claims[key] = value
        if path is not None:
            claim_paths[key] = path

    ai, ai_path = _nested_with_path(data, ("ai",), ("contribution", "ai"))
    if isinstance(ai, dict):
        allowed, allowed_path = _nested_with_path(ai, ("allowed",), ("assistance_allowed",))
        if isinstance(allowed, bool):
            record("ai_assistance", "allowed" if allowed else "prohibited", (ai_path or ()) + (allowed_path or ()))
        elif isinstance(allowed, str) and allowed in {"allowed", "prohibited", "unknown"}:
            record("ai_assistance", allowed, (ai_path or ()) + (allowed_path or ()))

        for key, claim_key in (("disclosure_locations", "disclosure_locations"), ("disclosure_stages", "disclosure_stages")):
            value, value_path = _nested_with_path(ai, (key,), ("disclosure", key.removeprefix("disclosure_")))
            if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
                record(claim_key, sorted(set(value)), (ai_path or ()) + (value_path or ()))

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
        value, value_path = _nested_with_path(data, *paths)
        if isinstance(value, bool):
            record(key, value, value_path)
    return claims, claim_paths


def _structured_match(text: str, path: tuple[str, ...]) -> re.Match[str] | None:
    """Find the parsed TOML assignment, scoped to its actual table path."""

    if not path:
        return None
    current_section: tuple[str, ...] = ()
    offset = 0
    table_pattern = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$")
    assignment_pattern = re.compile(r"^\s*([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?)\s*=")
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        table = table_pattern.match(line)
        if table:
            current_section = tuple(part.strip() for part in table.group(1).split("."))
        assignment = assignment_pattern.match(line)
        if assignment:
            assigned_path = current_section + tuple(part.strip() for part in assignment.group(1).split("."))
            if assigned_path == path:
                line_pattern = re.compile(r"^\s*" + re.escape(assignment.group(1)) + r"\s*=.*$", re.MULTILINE)
                return line_pattern.search(text, offset, offset + len(line))
        offset += len(raw_line)
    return None


def inspect_policy(root: Path) -> dict[str, Any]:
    root = root.resolve()
    document_sources: list[PolicySource] = []
    document_claims: dict[str, list[dict[str, Any]]] = {}
    for path in _candidate_document_paths(root):
        try:
            text = path.read_text(encoding="utf-8")
            claims, matches = _claims_from_document(text, path, root)
            provenance = {key: _provenance(path, root, text, key, matches.get(key)) for key in claims}
            document_sources.append(PolicySource(relative_path(path, root), "repository_document", claims, provenance=provenance))
            for key, value in claims.items():
                _claim(document_claims, key, value, path, root, text, matches.get(key))
        except OSError as exc:
            document_sources.append(PolicySource(relative_path(path, root), "repository_document", {}, str(exc)))

    structured_path = root / ".reviewworthy" / "policy.toml"
    structured_claims: dict[str, Any] = {}
    structured_error: str | None = None
    structured_provenance: dict[str, dict[str, Any]] = {}
    if structured_path.is_file():
        try:
            structured_text = structured_path.read_text(encoding="utf-8")
            structured_claims, structured_paths = _structured_claims(tomllib.loads(structured_text))
            structured_provenance = {
                key: _provenance(structured_path, root, structured_text, key, _structured_match(structured_text, structured_paths[key]))
                for key in structured_claims
            }
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
    claim_records: dict[str, dict[str, Any]] = {}
    for key in CLAIM_KEYS:
        values = {str(item["value"]): item["value"] for item in document_claims.get(key, [])}
        conflicting_key = any(conflict.get("key") == key for conflict in conflicts)
        provenance: list[dict[str, Any]] = [
            {field: item[field] for field in ("source", "line_start", "line_end", "match_start", "match_end", "excerpt_sha256") if field in item}
            for item in document_claims.get(key, [])
        ]
        if key in structured_provenance:
            provenance.append(structured_provenance[key])
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
        recorded_value = None if conflicting_key else authoritative[key]
        if recorded_value is None:
            state = "unknown"
        elif recorded_value is False or recorded_value == "prohibited":
            state = "false"
        else:
            state = "true"
        claim_records[key] = {
            "value": recorded_value,
            "state": state,
            "provenance": provenance,
        }

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
        "claim_records": claim_records,
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
