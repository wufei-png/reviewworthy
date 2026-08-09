"""Versioned public evidence summaries for Reviewworthy pull requests."""

from __future__ import annotations

import json
import re
from typing import Any

from .git import FINGERPRINT_ALGORITHM, PR_DIFF_FIELDS
from .repository import repository_slugs_match
from .util import canonical_json


SUMMARY_VERSION = "0.1"
SUMMARY_START = f"<!-- reviewworthy:evidence-summary:start:v{SUMMARY_VERSION} -->"
SUMMARY_END = f"<!-- reviewworthy:evidence-summary:end:v{SUMMARY_VERSION} -->"
_CONTRIBUTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SUMMARY_PATTERN = re.compile(
    re.escape(SUMMARY_START) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(SUMMARY_END),
    re.DOTALL,
)


class EvidenceSummaryError(ValueError):
    """A PR Body does not contain exactly one valid current evidence summary."""


def _repository_summary(packet: dict[str, Any]) -> dict[str, Any]:
    repository = packet.get("repository")
    if not isinstance(repository, dict):
        repository = {}
    owner = repository.get("owner") if isinstance(repository.get("owner"), str) else ""
    name = repository.get("name") if isinstance(repository.get("name"), str) else ""
    return {
        "slug": f"{owner}/{name}" if owner and name else "",
        "repository_id": repository.get("repository_id"),
    }


def _claim_summary(packet: dict[str, Any]) -> dict[str, Any]:
    verification = packet.get("verification")
    receipts = verification.get("receipts", []) if isinstance(verification, dict) else []
    plan_digest = verification.get("plan_digest") if isinstance(verification, dict) else None
    diff = packet.get("diff") if isinstance(packet.get("diff"), dict) else {}
    passed_receipts = [
        receipt
        for receipt in receipts
        if isinstance(receipt, dict)
        and receipt.get("receipt_version") == "0.3"
        and receipt.get("plan_digest") == plan_digest
        and receipt.get("subject_digest") == diff.get("subject_digest")
        and receipt.get("command_outcome") == "passed"
        and receipt.get("exit_code") == 0
        and receipt.get("integrity_status") == "stable"
        and receipt.get("provenance") == "contributor_local"
        and receipt.get("head_sha_before") == receipt.get("head_sha") == receipt.get("head_sha_after")
        and receipt.get("worktree_clean_before") is True
        and receipt.get("worktree_clean_after") is True
    ]
    review = packet.get("review") if isinstance(packet.get("review"), dict) else {}
    ownership = packet.get("ownership") if isinstance(packet.get("ownership"), dict) else {}
    ai_assistance = packet.get("ai_assistance") if isinstance(packet.get("ai_assistance"), dict) else {}
    disclosure = ai_assistance.get("disclosure") if isinstance(ai_assistance.get("disclosure"), dict) else {}
    return {
        "verification": {
            "claimed_outcome": "passed" if passed_receipts else "not_recorded",
            "receipt_count": len(passed_receipts),
        },
        "ownership": {
            "profile": review.get("profile", "standard"),
            "claimed_status": ownership.get("status", "not_recorded"),
        },
        "ai_disclosure": {
            "claimed_present": bool(str(disclosure.get("text", "")).strip()),
        },
    }


def build_evidence_summary(packet: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    """Project the private Packet into the minimal public PR evidence contract."""

    projected_diff = {field: diff.get(field) for field in PR_DIFF_FIELDS}
    return {
        "summary_version": SUMMARY_VERSION,
        "contribution_id": packet.get("contribution_id"),
        "repository": _repository_summary(packet),
        "diff": projected_diff,
        "claims": _claim_summary(packet),
    }


def validate_evidence_summary(summary: Any) -> dict[str, Any]:
    """Validate an arbitrary value without throwing on malformed input."""

    errors: list[dict[str, str]] = []

    def error(code: str, message: str, path: str) -> None:
        errors.append({"code": code, "message": message, "path": path})

    def reject_unknown(value: dict[str, Any], allowed: set[str], path: str) -> None:
        for key in sorted(set(value) - allowed):
            error("unknown_summary_field", f"{path}.{key} is not part of Evidence Summary {SUMMARY_VERSION}.", f"{path}.{key}")

    if not isinstance(summary, dict):
        error("invalid_evidence_summary", "Evidence Summary must be a JSON object.", "summary")
        return {"valid": False, "errors": errors}
    reject_unknown(summary, {"summary_version", "contribution_id", "repository", "diff", "claims"}, "summary")
    if summary.get("summary_version") != SUMMARY_VERSION:
        error("invalid_summary_version", f"summary_version must be {SUMMARY_VERSION}.", "summary_version")
    if not isinstance(summary.get("contribution_id"), str) or _CONTRIBUTION_ID_PATTERN.fullmatch(summary["contribution_id"]) is None:
        error("invalid_contribution_id", "contribution_id is not a current path-safe identifier.", "contribution_id")
    repository = summary.get("repository")
    if not isinstance(repository, dict):
        error("invalid_summary_repository", "repository must be an object.", "repository")
    else:
        reject_unknown(repository, {"slug", "repository_id"}, "repository")
        slug = repository.get("slug")
        if not isinstance(slug, str) or slug.count("/") != 1 or not all(part for part in slug.split("/")):
            error("invalid_summary_repository", "repository.slug must be owner/name.", "repository.slug")
        repository_id = repository.get("repository_id")
        if not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0:
            error("invalid_summary_repository_id", "repository.repository_id must be a positive integer.", "repository.repository_id")
    diff = summary.get("diff")
    if not isinstance(diff, dict):
        error("invalid_summary_diff", "diff must be an object.", "diff")
    else:
        reject_unknown(diff, set(PR_DIFF_FIELDS), "diff")
        for field in PR_DIFF_FIELDS:
            if field not in diff:
                error("missing_summary_diff_field", f"diff.{field} is required.", f"diff.{field}")
        if diff.get("comparison") != "merge_base":
            error("invalid_summary_comparison", "diff.comparison must be merge_base.", "diff.comparison")
        for field in ("base_tip_sha", "merge_base_sha", "head_sha", "subject_digest", "fingerprint_algorithm"):
            if not isinstance(diff.get(field), str) or not diff.get(field, "").strip():
                error("invalid_summary_diff_field", f"diff.{field} must be a non-empty string.", f"diff.{field}")
        if diff.get("fingerprint_algorithm") != FINGERPRINT_ALGORITHM:
            error(
                "invalid_summary_fingerprint_algorithm",
                f"diff.fingerprint_algorithm must be {FINGERPRINT_ALGORITHM}.",
                "diff.fingerprint_algorithm",
            )
        if not isinstance(diff.get("changed_files"), list) or not all(isinstance(path, str) and path for path in diff.get("changed_files", [])):
            error("invalid_summary_changed_files", "diff.changed_files must contain non-empty paths.", "diff.changed_files")
        for field in ("additions", "deletions"):
            value = diff.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                error("invalid_summary_line_count", f"diff.{field} must be a non-negative integer.", f"diff.{field}")
    claims = summary.get("claims")
    if not isinstance(claims, dict):
        error("invalid_summary_claims", "claims must be an object.", "claims")
    else:
        required_claims = {"verification", "ownership", "ai_disclosure"}
        reject_unknown(claims, required_claims, "claims")
        for claim in sorted(required_claims):
            if not isinstance(claims.get(claim), dict):
                error("invalid_summary_claim", f"claims.{claim} must be an object.", f"claims.{claim}")
    return {"valid": not errors, "errors": errors}


def render_evidence_summary(summary: dict[str, Any]) -> str:
    validation = validate_evidence_summary(summary)
    if not validation["valid"]:
        raise EvidenceSummaryError(f"Cannot render invalid Evidence Summary: {validation['errors']}")
    rendered = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{SUMMARY_START}\n```json\n{rendered}\n```\n{SUMMARY_END}"


def append_evidence_summary(body: str, summary: dict[str, Any]) -> str:
    if SUMMARY_START in body or SUMMARY_END in body:
        raise EvidenceSummaryError("PR Body already contains a Reviewworthy Evidence Summary marker")
    return body.rstrip() + "\n\n" + render_evidence_summary(summary)


def extract_evidence_summary(body: str) -> dict[str, Any]:
    if not isinstance(body, str):
        raise EvidenceSummaryError("PR Body must be text")
    matches = list(_SUMMARY_PATTERN.finditer(body))
    if len(matches) != 1:
        raise EvidenceSummaryError("PR Body must contain exactly one current Reviewworthy Evidence Summary")
    if body.count(SUMMARY_START) != 1 or body.count(SUMMARY_END) != 1:
        raise EvidenceSummaryError("PR Body contains unmatched or duplicate Evidence Summary markers")
    try:
        value = json.loads(matches[0].group(1))
    except json.JSONDecodeError as exc:
        raise EvidenceSummaryError(f"Evidence Summary contains invalid JSON: {exc}") from exc
    validation = validate_evidence_summary(value)
    if not validation["valid"]:
        raise EvidenceSummaryError(f"Evidence Summary is invalid: {validation['errors']}")
    return value


def summary_matches_repository(summary: dict[str, Any], slug: str, repository_id: int) -> bool:
    repository = summary.get("repository")
    return (
        isinstance(repository, dict)
        and repository_slugs_match(repository.get("slug"), slug)
        and repository.get("repository_id") == repository_id
    )


def canonical_summary(summary: dict[str, Any]) -> str:
    """Return the stable serialized form used by tests and operation identity."""

    return canonical_json(summary)
