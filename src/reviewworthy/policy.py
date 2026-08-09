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
from pathlib import PurePosixPath
import re
import tempfile
import tomllib
from typing import Any, Iterable

from .util import CommandOutputLimitError, CommandTimeoutError, relative_path, run_bounded


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


class PolicyTreeError(RuntimeError):
    """A runner-owned base commit cannot be inspected deterministically."""


@dataclass(frozen=True)
class PolicySource:
    path: str
    kind: str
    claims: dict[str, Any]
    error: str | None = None
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    ambiguities: list[dict[str, Any]] = field(default_factory=list)


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


def _policy_clause_ranges(text: str) -> list[tuple[int, int]]:
    repeated_subject = r"(?:an?\s+)?(?:ai\b|artificial intelligence|issues?\b|bug reports?\b|disclos|pr\b|pull request|security reports?\b|draft\b|work in progress|discovery\b|good[- ]first[- ]issue)"
    boundaries = re.finditer(
        rf"[.!?\n;,]+|\b(?:but|however|whereas)\b|\band\b(?=\s+{repeated_subject})",
        text,
        re.IGNORECASE,
    )
    ranges: list[tuple[int, int]] = []
    start = 0
    for boundary in boundaries:
        if start < boundary.start():
            ranges.append((start, boundary.start()))
        start = boundary.end()
    if start < len(text):
        ranges.append((start, len(text)))
    return ranges


def _clause_matches(text: str, patterns: Iterable[str]) -> list[re.Match[str]]:
    matches = [
        match
        for start, end in _policy_clause_ranges(text)
        for pattern in patterns
        for match in re.compile(pattern, re.IGNORECASE | re.DOTALL).finditer(text, start, end)
    ]
    return sorted(matches, key=lambda item: (item.start(), item.end()))


def _first_distinct_match(
    text: str,
    patterns: Iterable[str],
    excluded: Iterable[re.Match[str]],
) -> re.Match[str] | None:
    excluded_matches = list(excluded)
    for match in _clause_matches(text, patterns):
        # A broad positive pattern can land on the same terminal word as an
        # explicit negative within one clause (for example, "not required").
        # Ignore that duplicate parse; opposed clauses have distinct spans.
        if all(match.end() != item.end() for item in excluded_matches):
            return match
    return None


def _claims_from_document(
    text: str,
    path: Path,
    root: Path,
) -> tuple[dict[str, Any], dict[str, re.Match[str]], dict[str, list[tuple[Any, re.Match[str]]]]]:
    claims: dict[str, Any] = {}
    matches: dict[str, re.Match[str]] = {}
    ambiguities: dict[str, list[tuple[Any, re.Match[str]]]] = {}

    def record(key: str, value: Any, match: re.Match[str] | None) -> None:
        claims[key] = value
        if match:
            matches[key] = match

    def record_opposed(
        key: str,
        positive_value: Any,
        positive_patterns: Iterable[str],
        negative_value: Any,
        negative_patterns: Iterable[str],
    ) -> Any:
        negative_matches = [
            match
            for match in _clause_matches(text, negative_patterns)
            if not re.search(r"\bnot\s+(?:disallowed|forbidden|insufficient|optional|prohibited|unwelcome)\b", match.group(), re.IGNORECASE)
        ]
        negative_match = negative_matches[0] if negative_matches else None
        positive_match = _first_distinct_match(text, positive_patterns, negative_matches)
        if positive_match and negative_match:
            ambiguities[key] = [(positive_value, positive_match), (negative_value, negative_match)]
            return None
        if negative_match:
            record(key, negative_value, negative_match)
            return negative_value
        if positive_match:
            record(key, positive_value, positive_match)
            return positive_value
        return None

    record_opposed(
        "ai_assistance",
        "allowed",
        (
            r"\bai\b[^.!?\n]{0,80}?(?:(?<!not )permitted\b|(?<!not )(?<!un)welcome\b|(?<!dis)(?<!not )(?<!not-)allowed\b)",
            r"\bai\b[^.!?\n]{0,80}?(?:not\s+prohibited|not\s+forbidden|not\s+disallowed|not\s+unwelcome)\b",
        ),
        "prohibited",
        (
            r"\bno\s+(?:ai\b|artificial intelligence)[^.!?\n]{0,80}?(?:allowed|permitted|welcome)\b",
            r"\bai\b[^.!?\n]{0,80}?(?:not\s+allowed|(?<!not )disallowed|not\s+permitted|not\s+welcome|(?<!not )unwelcome|(?<!not )prohibited|(?<!not )forbidden|must\s+not|do\s+not\s+use|禁止|不得|不允许)",
            r"(?:do not|don't|must not|禁止|不得|不允许)[^.!?\n]{0,80}\bai\b",
        ),
    )
    record_opposed(
        "issue_required",
        True,
        (
            r"(?:issue|bug report)[^.!?\n]{0,50}?(?:is )?(?:required|must come first)",
            r"(?:an?\s+)?(?:issues?|bug reports?)\s+(?:(?:is|are)\s+)?not\s+optional\b",
            r"(?:open|file|create)\s+(?:an?\s+)?issue[^.!?\n]{0,50}(?:before|first|prior)",
            r"(?:contribution|pull request|pr)[^.!?\n]{0,50}must begin with[^.!?\n]{0,20}(?:an?\s+)?(?:public\s+)?(?:github\s+)?issue",
            r"(?:pull request|pr)[^.!?\n]{0,50}(?:not\s+accepted|may\s+not\s+proceed|cannot\s+proceed)[^.!?\n]{0,30}without[^.!?\n]{0,20}(?:an?\s+)?(?:issue|bug report)",
        ),
        False,
        (
            r"(?:an?\s+)?(?:issues?|bug reports?)\s+(?:(?:is|are)\s+)?(?:not\s+required|optional)\b",
            r"(?:issue|bug report)[^.!?\n]{0,30}?required\s+and\s+not\s+required\b",
            r"(?:do not|don't)[^.!?\n]{0,40}(?:need|have)[^.!?\n]{0,30}(?:issue|bug report)",
            r"(?:you|contributors?)[^.!?\n]{0,30}(?:are\s+)?not\s+required\s+to[^.!?\n]{0,20}(?:open|file|create)[^.!?\n]{0,20}(?:an?\s+)?issue",
            r"(?:pull request|pr)[^.!?\n]{0,40}(?:may|can)\s+(?:be\s+)?(?:opened|submitted|created|proceed)[^.!?\n]{0,30}without[^.!?\n]{0,20}(?:an?\s+)?(?:issue|bug report)",
            r"(?:pull request|pr)[^.!?\n]{0,40}does not require[^.!?\n]{0,20}(?:an?\s+)?(?:issue|bug report)",
        ),
    )
    disclosure_value = record_opposed(
        "disclosure_required",
        True,
        (
            r"(?:must|should|required|please)[^.!?\n]{0,50}?(?:disclos|declare|mention)[^.!?\n]{0,50}?(?:\bai\b|artificial intelligence)",
            r"(?:disclos|declare|mention)[^.!?\n]{0,50}?(?:\bai\b|artificial intelligence)[^.!?\n]{0,50}?(?:required|must)",
            r"(?:\bai\b|artificial intelligence)[^.!?\n]{0,50}?(?:must|should|required)[^.!?\n]{0,50}?(?:disclos|declare|mention)",
            r"(?:\bai\b|artificial intelligence)[^.!?\n]{0,30}(?:disclosure|declaration)[^.!?\n]{0,20}(?:is|are)\s+not\s+optional\b",
            r"(?:disclosure|declaration)[^.!?\n]{0,20}(?:of\s+)?(?:\bai\b|artificial intelligence)[^.!?\n]{0,20}(?:is|are)\s+not\s+optional\b",
        ),
        False,
        (
            r"(?:\bai\b|artificial intelligence)[^.!?\n]{0,60}(?:disclosure|declaration)[^.!?\n]{0,30}(?:not\s+required|optional)",
            r"(?:disclosure|declaration)[^.!?\n]{0,20}(?:of\s+)?(?:\bai\b|artificial intelligence)[^.!?\n]{0,20}(?:is|are)\s+(?:not\s+required|optional)",
            r"(?:disclosure|declaration)[^.!?\n]{0,30}(?:\bai\b|artificial intelligence)[^.!?\n]{0,20}required\s+and\s+not\s+required\b",
            r"(?:you|contributors?)[^.!?\n]{0,30}(?:are\s+)?not\s+required\s+to[^.!?\n]{0,20}(?:disclos|declare|mention)[^.!?\n]{0,40}(?:\bai\b|artificial intelligence)",
            r"(?:do not|don't)[^.!?\n]{0,40}(?:need|have)[^.!?\n]{0,30}(?:disclos|declare|mention)[^.!?\n]{0,40}(?:\bai\b|artificial intelligence)",
            r"(?:contributors?|you)[^.!?\n]{0,30}(?:must\s+not|cannot|may\s+not)[^.!?\n]{0,20}(?:disclos|declare|mention)[^.!?\n]{0,40}(?:\bai\b|artificial intelligence)",
        ),
    )
    if disclosure_value is True:
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
            record("disclosure_locations", sorted(set(locations)), location_matches[0])

    record_opposed(
        "human_pr_narrative_required",
        True,
        (
            r"(?:pr|pull request)[^.!?\n]{0,100}?(?:own words|your own|human[- ]written)",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,100}(?:must not|cannot|should not)[^.!?\n]{0,50}(?:pr|pull request|description)",
            r"(?:pr|pull request)[^.!?\n]{0,60}(?:must not|cannot|may not)[^.!?\n]{0,30}(?:be\s+)?(?:ai[- ]written|generated by ai)",
            r"(?:human[- ]written|own words|your own words)[^.!?\n]{0,50}(?:pr|pull request|description|narrative)[^.!?\n]{0,20}not\s+optional\b",
        ),
        False,
        (
            r"(?:human[- ]written|own words|your own words)[^.!?\n]{0,50}(?:not\s+required|optional)",
            r"(?:pr|pull request)[^.!?\n]{0,40}(?:human[- ]written|own words)[^.!?\n]{0,20}required\s+and\s+not\s+required\b",
            r"(?:pr|pull request)[^.!?\n]{0,60}(?:must not|cannot|may not)[^.!?\n]{0,30}(?:be\s+)?human[- ]written",
            r"(?:pr|pull request)[^.!?\n]{0,30}(?:description|narrative)?[^.!?\n]{0,20}(?:does not need|need not)[^.!?\n]{0,20}(?:to be\s+)?human[- ]written",
            r"(?:pr|pull request)[^.!?\n]{0,50}(?:may|can)\b\s+(?:be\s+)?(?:ai[- ]written|generated by ai)",
        ),
    )
    record_opposed(
        "security_private_reporting",
        True,
        (
            r"security[^.!?\n]{0,100}?(?:private|email|do not (?:open|file)[^.!?\n]{0,30}(?:public|issue))",
            r"(?:private|email)[^.!?\n]{0,60}security report",
            r"security reports?[^.!?\n]{0,60}(?:must not|cannot|may not)[^.!?\n]{0,30}(?:be\s+)?public",
        ),
        False,
        (
            r"security reports?[^.!?\n]{0,60}(?:do not need|need not)[^.!?\n]{0,30}(?:private|email)",
            r"security reports?[^.!?\n]{0,40}(?:are\s+)?not\s+required\s+to\s+be[^.!?\n]{0,20}private",
            r"security reports?[^.!?\n]{0,60}(?:must not|cannot|may not)[^.!?\n]{0,30}(?:be\s+)?private",
            r"security reports?[^.!?\n]{0,50}(?:may|can)\b\s+(?:be\s+)?(?:public|filed publicly)",
        ),
    )
    record_opposed(
        "draft_pr_required",
        True,
        (
            r"(?:draft|work in progress)[^.!?\n]{0,80}?(?:pr|pull request)[^.!?\n]{0,60}?(?:required|must)",
            r"(?:draft|work in progress)[^.!?\n]{0,80}(?:pr|pull request)[^.!?\n]{0,30}not\s+optional\b",
        ),
        False,
        (
            r"(?:draft|work in progress)[^.!?\n]{0,80}(?:pr|pull request)[^.!?\n]{0,40}(?:not\s+required|optional)",
            r"(?:draft|work in progress)[^.!?\n]{0,80}(?:pr|pull request)[^.!?\n]{0,30}required\s+and\s+not\s+required\b",
            r"(?:pr|pull request)[^.!?\n]{0,60}(?:need not|does not need to)[^.!?\n]{0,30}(?:draft|work in progress)",
            r"(?:pr|pull request)[^.!?\n]{0,40}(?:is|are)\s+not\s+required\s+to\s+be[^.!?\n]{0,20}(?:draft|work in progress)",
        ),
    )
    record_opposed(
        "discovery_evidence_allowed",
        True,
        (
            r"discovery[^.!?\n]{0,100}?(?:evidence|reproduction)[^.!?\n]{0,100}?(?:(?<!in)(?<!not )sufficient\b|enough|(?<!dis)(?<!not )allowed\b)",
            r"discovery[^.!?\n]{0,100}?(?:evidence|reproduction)[^.!?\n]{0,80}?(?:not\s+insufficient|not\s+disallowed|not\s+prohibited|not\s+forbidden)\b",
            r"reproducible[^.!?\n]{0,100}(?:defect|failure)[^.!?\n]{0,100}(?:may|can)[^.!?\n]{0,50}(?:pr|contribution)",
        ),
        False,
        (
            r"discovery[^.!?\n]{0,100}?(?:evidence|reproduction)[^.!?\n]{0,80}?(?:not\s+allowed|(?<!not )disallowed|prohibited|(?<!not )insufficient|not\s+sufficient|not\s+enough)",
            r"(?:do not|don't)[^.!?\n]{0,60}(?:accept|allow)[^.!?\n]{0,60}discovery[^.!?\n]{0,40}(?:evidence|reproduction)",
        ),
    )
    record_opposed(
        "good_first_issue_ai_allowed",
        True,
        (
            r"good[- ]first[- ]issue[^.!?\n]{0,120}?(?:ai|artificial intelligence)[^.!?\n]{0,60}?(?:(?<!not )permitted\b|(?<!not )(?<!un)welcome\b|(?<!dis)(?<!not )(?<!not-)allowed\b)",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,120}?good[- ]first[- ]issue[^.!?\n]{0,60}?(?:(?<!not )permitted\b|(?<!not )(?<!un)welcome\b|(?<!dis)(?<!not )(?<!not-)allowed\b)",
            r"good[- ]first[- ]issue[^.!?\n]{0,120}?(?:ai|artificial intelligence)[^.!?\n]{0,60}?(?:not\s+prohibited|not\s+forbidden|not\s+disallowed|not\s+unwelcome)\b",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,120}?good[- ]first[- ]issue[^.!?\n]{0,60}?(?:not\s+prohibited|not\s+forbidden|not\s+disallowed|not\s+unwelcome)\b",
        ),
        False,
        (
            r"good[- ]first[- ]issue[^.!?\n]{0,120}?(?:ai|artificial intelligence)[^.!?\n]{0,60}?(?:not\s+allowed|(?<!not )disallowed|not\s+permitted|not\s+welcome|(?<!not )unwelcome|(?<!not )prohibited|(?<!not )forbidden|must\s+not)",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,120}?good[- ]first[- ]issue[^.!?\n]{0,60}?(?:not\s+allowed|(?<!not )disallowed|not\s+permitted|not\s+welcome|(?<!not )unwelcome|(?<!not )prohibited|(?<!not )forbidden|must\s+not)",
            r"(?:ai|artificial intelligence)[^.!?\n]{0,60}?(?:not\s+allowed|(?<!not )disallowed|not\s+permitted|not\s+welcome|(?<!not )unwelcome|(?<!not )prohibited|(?<!not )forbidden|must\s+not)[^.!?\n]{0,80}?good[- ]first[- ]issue",
        ),
    )

    return claims, matches, ambiguities


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


def _is_policy_tree_path(path: str) -> bool:
    value = PurePosixPath(path)
    if value.is_absolute() or ".." in value.parts:
        return False
    if path == ".reviewworthy/policy.toml":
        return True
    if len(value.parts) == 1 and value.name in {
        "README.md", "README", "CONTRIBUTING.md", "CONTRIBUTING", "AGENTS.md", "SECURITY.md",
    }:
        return True
    if value.parts and value.parts[0] == ".github":
        return "workflows" not in value.parts and value.suffix.lower() in {".md", ".markdown", ".txt", ".yml", ".yaml"}
    if value.parts and value.parts[0] == "docs":
        return not (len(value.parts) > 1 and value.parts[1] == "adr") and value.suffix.lower() in {".md", ".markdown"}
    return False


def inspect_policy_at_commit(root: Path, commit_sha: str) -> dict[str, Any]:
    """Inspect policy sources from one immutable Git tree, never the PR head."""

    if not isinstance(commit_sha, str) or re.fullmatch(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?", commit_sha) is None:
        raise PolicyTreeError("base commit must be a full 40- or 64-character hexadecimal object ID")
    root = root.resolve()

    def git(*args: str) -> bytes:
        try:
            completed = run_bounded(
                ["git", "-C", str(root), *args],
                timeout_seconds=60,
                max_capture_bytes=16 * 1024 * 1024,
            )
        except (OSError, CommandTimeoutError, CommandOutputLimitError) as exc:
            raise PolicyTreeError(str(exc)) from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip() or "git command failed"
            raise PolicyTreeError(detail)
        return completed.stdout

    resolved = git("rev-parse", "--verify", f"{commit_sha}^{{commit}}").decode("ascii", errors="strict").strip()
    if resolved.lower() != commit_sha.lower():
        raise PolicyTreeError("base commit identity did not resolve exactly")
    names = git("ls-tree", "-r", "--name-only", commit_sha).decode("utf-8", errors="surrogateescape").splitlines()
    selected = [name for name in names if _is_policy_tree_path(name)]
    with tempfile.TemporaryDirectory(prefix="reviewworthy-policy-") as directory:
        snapshot = Path(directory)
        for name in selected:
            destination = snapshot.joinpath(*PurePosixPath(name).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(git("show", f"{commit_sha}:{name}"))
        result = inspect_policy(snapshot)
    result["repository"] = str(root)
    result["base_sha"] = commit_sha.lower()
    return result


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
    document_ambiguities: list[dict[str, Any]] = []
    for path in _candidate_document_paths(root):
        try:
            text = path.read_text(encoding="utf-8")
            claims, matches, ambiguities = _claims_from_document(text, path, root)
            provenance = {key: _provenance(path, root, text, key, matches.get(key)) for key in claims}
            source_ambiguities = [
                {
                    "key": key,
                    "kind": "single_repository_document",
                    "source": relative_path(path, root),
                    "claims": [
                        {"value": value, **_provenance(path, root, text, key, match)}
                        for value, match in opposed
                    ],
                }
                for key, opposed in ambiguities.items()
            ]
            document_ambiguities.extend(source_ambiguities)
            document_sources.append(PolicySource(relative_path(path, root), "repository_document", claims, provenance=provenance, ambiguities=source_ambiguities))
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
        ambiguous_claims = [ambiguity for ambiguity in document_ambiguities if ambiguity.get("key") == key]
        provenance: list[dict[str, Any]] = [
            {field: item[field] for field in ("source", "line_start", "line_end", "match_start", "match_end", "excerpt_sha256") if field in item}
            for item in document_claims.get(key, [])
        ]
        if key in structured_provenance:
            provenance.append(structured_provenance[key])
        for ambiguity in ambiguous_claims:
            provenance.extend(
                {field: item[field] for field in ("source", "line_start", "line_end", "match_start", "match_end", "excerpt_sha256") if field in item}
                for item in ambiguity.get("claims", [])
            )
        if ambiguous_claims:
            authoritative[key] = None
            unknown.append(key)
        elif len(values) == 1:
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
        recorded_value = None if conflicting_key or ambiguous_claims else authoritative[key]
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

    posture = "conservative" if unknown or conflicts or document_ambiguities else "explicit"
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
        "ambiguities": document_ambiguities,
        "hard_stops": (
            ([{"code": "policy_conflict", "reason": "Policy sources contradict each other."}] if conflicts else [])
            + ([{"code": "policy_ambiguity", "reason": "One policy source makes opposed explicit claims."}] if document_ambiguities else [])
        ),
        "posture": posture,
        "disclosure": {
            "required": authoritative.get("disclosure_required") is True or posture == "conservative",
            "locations": disclosure_locations,
            "stages": disclosure_stages,
        },
        "result": "blocked" if conflicts or document_ambiguities else "passed",
    }
