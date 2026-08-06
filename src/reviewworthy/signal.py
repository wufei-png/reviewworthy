"""Contribution Signal artifacts and lifecycle validation."""

from __future__ import annotations

from typing import Any


SIGNAL_VERSION = "0.1"
SIGNAL_KINDS = {
    "issue",
    "maintainer-request",
    "accepted-proposal",
    "discussion",
    "reproducible-evidence",
}
SIGNAL_STATUSES = {"pending", "confirmed", "rejected", "expired"}


def skeleton_signal(kind: str = "issue", reference: str = "") -> dict[str, Any]:
    """Create a status-bearing signal record for a selected contribution."""

    return {
        "signal_version": SIGNAL_VERSION,
        "kind": kind,
        "reference": reference,
        "status": "pending",
        "evidence": [],
        "published": False,
        "confirmed_by": "",
        "confirmed_at": "",
    }


def _error(errors: list[dict[str, str]], code: str, message: str, path: str) -> None:
    errors.append({"code": code, "message": message, "path": path})


def validate_signal(signal: dict[str, Any], *, require_confirmed: bool = False) -> dict[str, Any]:
    """Validate structure and, optionally, readiness of a Contribution Signal."""

    errors: list[dict[str, str]] = []
    if signal.get("signal_version") != SIGNAL_VERSION:
        _error(errors, "unsupported_signal_version", "signal_version must be 0.1", "signal.signal_version")
    if signal.get("kind") not in SIGNAL_KINDS:
        _error(errors, "invalid_signal_kind", f"signal.kind must be one of {sorted(SIGNAL_KINDS)}", "signal.kind")
    if not isinstance(signal.get("reference"), str) or not signal.get("reference", "").strip():
        _error(errors, "missing_signal_reference", "signal.reference is required", "signal.reference")
    if signal.get("status") not in SIGNAL_STATUSES:
        _error(errors, "invalid_signal_status", f"signal.status must be one of {sorted(SIGNAL_STATUSES)}", "signal.status")

    evidence = signal.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(item, str) and item.strip() for item in evidence):
        _error(errors, "invalid_signal_evidence", "signal.evidence must be a list of non-empty strings", "signal.evidence")
    elif signal.get("kind") == "reproducible-evidence" and not evidence:
        _error(errors, "missing_signal_evidence", "Reproducible evidence signals need evidence records", "signal.evidence")

    published = signal.get("published")
    if not isinstance(published, bool):
        _error(errors, "invalid_signal_publication", "signal.published must be boolean", "signal.published")
    elif signal.get("kind") != "reproducible-evidence" and published is not True:
        _error(errors, "signal_not_published", "Issue, maintainer-request, accepted-proposal, and discussion signals need a public reference", "signal.published")

    for key in ("confirmed_by", "confirmed_at"):
        value = signal.get(key, "")
        if value and not isinstance(value, str):
            _error(errors, f"invalid_signal_{key}", f"signal.{key} must be a string when present", f"signal.{key}")

    if signal.get("status") == "confirmed":
        if not isinstance(signal.get("confirmed_at"), str) or not signal.get("confirmed_at", "").strip():
            _error(errors, "missing_signal_confirmation_time", "A confirmed signal needs confirmed_at", "signal.confirmed_at")
        if signal.get("kind") in {"maintainer-request", "accepted-proposal", "discussion"} and not str(signal.get("confirmed_by", "")).strip():
            _error(errors, "missing_signal_confirmer", "This signal needs the confirming maintainer or project actor", "signal.confirmed_by")

    if require_confirmed and signal.get("status") != "confirmed":
        _error(errors, "signal_not_confirmed", "The Contribution Signal must be confirmed before implementation or remote readiness", "signal.status")

    return {"valid": not errors, "errors": errors}


def validate_basis_signal(basis: dict[str, Any], mode: str) -> list[dict[str, str]]:
    """Validate the signal required by a selected basis and entry mode."""

    errors: list[dict[str, str]] = []
    kind = basis.get("kind")
    if mode == "discovery" and kind not in {"signal", "discovery-evidence"}:
        _error(errors, "discovery_signal_required", "Discovery entries need a confirmed signal or policy-permitted reproducible-evidence basis", "basis.kind")

    requires_record = kind in {"signal", "discovery-evidence"}
    if not requires_record:
        return errors

    signal = basis.get("signal")
    if not isinstance(signal, dict):
        _error(errors, "missing_signal_record", "This contribution basis needs a structured signal record", "basis.signal")
        return errors

    signal_result = validate_signal(signal)
    for error in signal_result["errors"]:
        errors.append({**error, "path": error["path"].replace("signal", "basis.signal", 1)})
    if kind == "discovery-evidence" and signal.get("kind") != "reproducible-evidence":
        _error(errors, "discovery_signal_kind_mismatch", "discovery-evidence basis must use a reproducible-evidence signal", "basis.signal.kind")
    return errors


def signal_readiness_blockers(basis: dict[str, Any], mode: str) -> list[dict[str, str]]:
    """Return lifecycle blockers without changing structural packet validation."""

    if mode not in {"issue-backed", "discovery"}:
        return []
    if mode == "discovery" and basis.get("kind") not in {"signal", "discovery-evidence"}:
        return [{"code": "discovery_signal_required", "message": "Discovery work cannot enter implementation without a signal.", "path": "basis.kind"}]
    if basis.get("kind") not in {"signal", "discovery-evidence"}:
        return []
    signal = basis.get("signal")
    if not isinstance(signal, dict):
        return [{"code": "missing_signal_record", "message": "The selected contribution basis has no structured signal record.", "path": "basis.signal"}]
    if signal.get("status") in {"rejected", "expired"}:
        return [{"code": "signal_unavailable", "message": "The Contribution Signal was rejected or expired.", "path": "basis.signal.status"}]
    return []
