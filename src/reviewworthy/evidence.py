"""Versioned public evidence summaries for Reviewworthy pull requests."""

from __future__ import annotations

import json
import re
from typing import Any

from .git import FINGERPRINT_ALGORITHM, PR_DIFF_FIELDS
from .repository import repository_slugs_match
from .util import canonical_json


SUMMARY_VERSION = "0.1"
SUMMARY_PROFILES = {"standard", "heightened", "learning"}
SUMMARY_OWNERSHIP_STATUSES = {"passed", "failed", "blocked", "unknown", "not_run", "not_recorded"}
SUMMARY_START = f"<!-- reviewworthy:evidence-summary:start:v{SUMMARY_VERSION} -->"
SUMMARY_END = f"<!-- reviewworthy:evidence-summary:end:v{SUMMARY_VERSION} -->"
OVERVIEW_START = f"<!-- reviewworthy:evidence-overview:start:v{SUMMARY_VERSION} -->"
OVERVIEW_END = f"<!-- reviewworthy:evidence-overview:end:v{SUMMARY_VERSION} -->"
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
        verification_claim = claims.get("verification")
        if isinstance(verification_claim, dict):
            reject_unknown(verification_claim, {"claimed_outcome", "receipt_count"}, "claims.verification")
            if verification_claim.get("claimed_outcome") not in {"passed", "not_recorded"}:
                error(
                    "invalid_summary_verification_claim",
                    "claims.verification.claimed_outcome must be passed or not_recorded.",
                    "claims.verification.claimed_outcome",
                )
            receipt_count = verification_claim.get("receipt_count")
            if not isinstance(receipt_count, int) or isinstance(receipt_count, bool) or receipt_count < 0:
                error(
                    "invalid_summary_receipt_count",
                    "claims.verification.receipt_count must be a non-negative integer.",
                    "claims.verification.receipt_count",
                )
            elif (
                (verification_claim.get("claimed_outcome") == "passed" and receipt_count == 0)
                or (verification_claim.get("claimed_outcome") == "not_recorded" and receipt_count != 0)
            ):
                error(
                    "inconsistent_summary_verification_claim",
                    "A passed claim needs at least one receipt; not_recorded needs zero receipts.",
                    "claims.verification",
                )
        ownership_claim = claims.get("ownership")
        if isinstance(ownership_claim, dict):
            reject_unknown(ownership_claim, {"profile", "claimed_status"}, "claims.ownership")
            if ownership_claim.get("profile") not in SUMMARY_PROFILES:
                error("invalid_summary_profile", "claims.ownership.profile is not recognized.", "claims.ownership.profile")
            if ownership_claim.get("claimed_status") not in SUMMARY_OWNERSHIP_STATUSES:
                error(
                    "invalid_summary_ownership_status",
                    "claims.ownership.claimed_status is not recognized.",
                    "claims.ownership.claimed_status",
                )
        disclosure_claim = claims.get("ai_disclosure")
        if isinstance(disclosure_claim, dict):
            reject_unknown(disclosure_claim, {"claimed_present"}, "claims.ai_disclosure")
            if not isinstance(disclosure_claim.get("claimed_present"), bool):
                error(
                    "invalid_summary_disclosure_claim",
                    "claims.ai_disclosure.claimed_present must be a boolean.",
                    "claims.ai_disclosure.claimed_present",
                )
    return {"valid": not errors, "errors": errors}


def render_evidence_summary(summary: dict[str, Any]) -> str:
    validation = validate_evidence_summary(summary)
    if not validation["valid"]:
        raise EvidenceSummaryError(f"Cannot render invalid Evidence Summary: {validation['errors']}")
    rendered = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{SUMMARY_START}\n```json\n{rendered}\n```\n{SUMMARY_END}"


def render_evidence_overview(summary: dict[str, Any], *, workflow_ready: bool | None = None) -> str:
    """Render a human-readable projection without upgrading contributor claims."""

    validation = validate_evidence_summary(summary)
    if not validation["valid"]:
        raise EvidenceSummaryError(f"Cannot render invalid Evidence Summary: {validation['errors']}")
    diff = summary["diff"]
    claims = summary["claims"]
    verification = claims["verification"]
    ownership = claims["ownership"]
    disclosure = claims["ai_disclosure"]
    if workflow_ready is True:
        readiness = "Ready for maintainer review"
    elif workflow_ready is False:
        readiness = "Not yet ready for maintainer review"
    else:
        readiness = "Readiness not evaluated by this projection"
    file_count = len(diff["changed_files"])
    file_label = "file" if file_count == 1 else "files"
    verification_text = (
        f"Contributor claims {verification['receipt_count']} current verification "
        f"{'receipt' if verification['receipt_count'] == 1 else 'receipts'} passed."
        if verification["claimed_outcome"] == "passed"
        else "Contributor has not recorded a current passing verification receipt."
    )
    ownership_text = (
        f"Contributor claims `{ownership['claimed_status']}` under the `{ownership['profile']}` review profile."
    )
    disclosure_text = (
        "Contributor claims an AI-assistance disclosure is present."
        if disclosure["claimed_present"]
        else "Contributor does not claim that an AI-assistance disclosure is present."
    )
    return "\n".join([
        OVERVIEW_START,
        "## Reviewworthy contribution evidence",
        "",
        f"**Contributor workflow:** {readiness}",
        "",
        f"- **Contribution:** `{summary['contribution_id']}`",
        f"- **Scope:** {file_count} changed {file_label}, +{diff['additions']} / -{diff['deletions']} lines",
        f"- **Verification:** {verification_text}",
        f"- **Ownership:** {ownership_text}",
        f"- **AI assistance:** {disclosure_text}",
        "",
        "The read-only Action recomputes repository and Diff facts from the machine-readable block below. "
        "Verification, ownership, and disclosure remain contributor claims.",
        OVERVIEW_END,
    ])


def append_evidence_summary(
    body: str,
    summary: dict[str, Any],
    *,
    workflow_ready: bool | None = None,
) -> str:
    markers = (SUMMARY_START, SUMMARY_END, OVERVIEW_START, OVERVIEW_END)
    if any(marker in body for marker in markers):
        raise EvidenceSummaryError("PR Body already contains a Reviewworthy evidence marker")
    overview = render_evidence_overview(summary, workflow_ready=workflow_ready)
    return body.rstrip() + "\n\n" + overview + "\n\n" + render_evidence_summary(summary)


def extract_evidence_summary(body: str) -> dict[str, Any]:
    if not isinstance(body, str):
        raise EvidenceSummaryError("PR Body must be text")
    overview_counts = (body.count(OVERVIEW_START), body.count(OVERVIEW_END))
    if overview_counts not in {(0, 0), (1, 1)}:
        raise EvidenceSummaryError("PR Body contains unmatched or duplicate evidence overview markers")
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
