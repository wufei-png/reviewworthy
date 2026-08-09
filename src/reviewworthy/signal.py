"""Orthogonal Contribution Signal records for Packet 0.3."""

from __future__ import annotations

from typing import Any

from .repository import parse_public_record


SIGNAL_VERSION = "0.3"
SIGNAL_RECORD_TYPES = {"issue", "pull_request", "discussion", "local_evidence"}
SIGNAL_CLAIM_TYPES = {"bug_report", "maintainer_request", "accepted_proposal", "reproducible_evidence"}
SIGNAL_LIFECYCLES = {"pending", "confirmed", "rejected", "expired"}
SIGNAL_VERIFICATION_STATUSES = {"verified", "local_only"}
SIGNAL_AUTHORITY_KINDS = {"contributor", "maintainer", "repository"}


def require_current_signal(signal: Any) -> dict[str, Any]:
    """Reject non-0.3 Signal records before interpreting any other field."""

    if not isinstance(signal, dict) or signal.get("signal_version") != SIGNAL_VERSION:
        raise ValueError(f"Only Signal {SIGNAL_VERSION} is supported; older formats are not read or migrated")
    return signal


def skeleton_signal(
    record_type: str = "issue",
    claim_type: str = "bug_report",
    reference: str = "",
) -> dict[str, Any]:
    """Create an explicit current-format signal with independent axes."""

    return {
        "signal_version": SIGNAL_VERSION,
        "record_type": record_type,
        "claim_type": claim_type,
        "lifecycle": "pending",
        "reference": reference,
        "evidence": [],
        "authority": {"kind": "contributor", "actor": "", "asserted_at": ""},
    }


def _error(errors: list[dict[str, str]], code: str, message: str, path: str) -> None:
    errors.append({"code": code, "message": message, "path": path})


def validate_signal(signal: Any, *, require_confirmed: bool = False) -> dict[str, Any]:
    """Validate only Signal 0.3; earlier axes are unknown fields, not aliases."""

    errors: list[dict[str, str]] = []
    if not isinstance(signal, dict):
        _error(errors, "invalid_signal", "Signal must be an object", "signal")
        return {"valid": False, "errors": errors}
    if signal.get("signal_version") != SIGNAL_VERSION:
        _error(errors, "invalid_signal_version", f"signal_version must be {SIGNAL_VERSION}", "signal.signal_version")
        return {"valid": False, "errors": errors}
    allowed = {
        "signal_version", "record_type", "claim_type", "lifecycle", "reference", "evidence",
        "authority", "verification", "publication_subject_id", "publication",
    }
    for key in sorted(set(signal) - allowed):
        _error(errors, "unknown_signal_field", f"signal.{key} is not part of Signal {SIGNAL_VERSION}", f"signal.{key}")
    record_type = signal.get("record_type")
    claim_type = signal.get("claim_type")
    lifecycle = signal.get("lifecycle")
    if record_type not in SIGNAL_RECORD_TYPES:
        _error(errors, "invalid_signal_record_type", f"record_type must be one of {sorted(SIGNAL_RECORD_TYPES)}", "signal.record_type")
    if claim_type not in SIGNAL_CLAIM_TYPES:
        _error(errors, "invalid_signal_claim_type", f"claim_type must be one of {sorted(SIGNAL_CLAIM_TYPES)}", "signal.claim_type")
    if lifecycle not in SIGNAL_LIFECYCLES:
        _error(errors, "invalid_signal_lifecycle", f"lifecycle must be one of {sorted(SIGNAL_LIFECYCLES)}", "signal.lifecycle")
    reference = signal.get("reference")
    if not isinstance(reference, str):
        _error(errors, "invalid_signal_reference", "reference must be a string", "signal.reference")
    elif record_type != "local_evidence" and not reference.strip():
        _error(errors, "missing_signal_reference", "External signal records require a public reference", "signal.reference")
    elif record_type != "local_evidence":
        parsed = parse_public_record(reference)
        if not parsed or parsed.get("record_type") != record_type:
            _error(errors, "signal_reference_record_mismatch", "reference must be a canonical GitHub URL for record_type", "signal.reference")
    evidence = signal.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) and item.strip() for item in evidence):
        _error(errors, "invalid_signal_evidence", "evidence must be a list of non-empty strings", "signal.evidence")
    elif claim_type == "reproducible_evidence" and not evidence:
        _error(errors, "missing_signal_evidence", "A reproducible_evidence claim needs evidence", "signal.evidence")
    if record_type == "local_evidence" and claim_type != "reproducible_evidence":
        _error(errors, "local_signal_claim_mismatch", "local_evidence records must claim reproducible_evidence", "signal.claim_type")

    authority = signal.get("authority")
    if not isinstance(authority, dict):
        _error(errors, "invalid_signal_authority", "authority must be an object", "signal.authority")
    else:
        for key in sorted(set(authority) - {"kind", "actor", "asserted_at"}):
            _error(errors, "unknown_signal_authority_field", f"authority.{key} is not current", f"signal.authority.{key}")
        if authority.get("kind") not in SIGNAL_AUTHORITY_KINDS:
            _error(errors, "invalid_signal_authority_kind", f"authority.kind must be one of {sorted(SIGNAL_AUTHORITY_KINDS)}", "signal.authority.kind")
        for key in ("actor", "asserted_at"):
            if not isinstance(authority.get(key), str):
                _error(errors, "invalid_signal_authority", f"authority.{key} must be a string", f"signal.authority.{key}")
        if lifecycle == "confirmed" and claim_type in {"maintainer_request", "accepted_proposal"}:
            if authority.get("kind") not in {"maintainer", "repository"}:
                _error(errors, "insufficient_signal_authority", "Confirmed maintainer claims require maintainer or repository authority", "signal.authority.kind")
            if not str(authority.get("actor", "")).strip() or not str(authority.get("asserted_at", "")).strip():
                _error(errors, "missing_signal_authority", "Confirmed maintainer claims require actor and asserted_at", "signal.authority")

    verification = signal.get("verification")
    if verification is not None:
        if not isinstance(verification, dict):
            _error(errors, "invalid_signal_verification", "verification must be an object", "signal.verification")
        else:
            verification_fields = {
                "status", "provider", "reference", "record_type", "verified_at", "host", "repository",
                "repository_id", "number", "url", "visibility", "state", "state_reason", "locked", "labels",
            }
            for key in sorted(set(verification) - verification_fields):
                _error(errors, "unknown_signal_verification_field", f"verification.{key} is not current", f"signal.verification.{key}")
            if verification.get("status") not in SIGNAL_VERIFICATION_STATUSES:
                _error(errors, "invalid_signal_verification_status", "verification.status must be verified or local_only", "signal.verification.status")
            if verification.get("reference") != reference:
                _error(errors, "stale_signal_verification", "verification.reference must match reference", "signal.verification.reference")
            if not isinstance(verification.get("verified_at"), str) or not verification.get("verified_at", "").strip():
                _error(errors, "missing_signal_verification_time", "verification.verified_at is required", "signal.verification.verified_at")
            if record_type == "local_evidence":
                if verification.get("status") != "local_only" or verification.get("provider") != "local" or verification.get("record_type") != "local_evidence":
                    _error(errors, "signal_verification_record_mismatch", "local_evidence requires local_only/local verification", "signal.verification")
            elif verification.get("status") != "verified" or verification.get("provider") != "github" or verification.get("record_type") != record_type:
                _error(errors, "signal_verification_record_mismatch", "External verification must be verified by GitHub for the same record_type", "signal.verification")

    subject_id = signal.get("publication_subject_id")
    publication = signal.get("publication")
    if (subject_id is None) != (publication is None):
        _error(errors, "incomplete_signal_publication", "publication_subject_id and publication must be recorded together", "signal.publication")
    if subject_id is not None and (not isinstance(subject_id, str) or not subject_id.strip()):
        _error(errors, "invalid_signal_publication_subject", "publication_subject_id must be a non-empty string", "signal.publication_subject_id")
    if publication is not None:
        if not isinstance(publication, dict):
            _error(errors, "invalid_signal_publication", "publication must be an object", "signal.publication")
        else:
            for key in sorted(set(publication) - {"operation_id", "repo", "title", "body"}):
                _error(errors, "unknown_signal_publication_field", f"publication.{key} is not current", f"signal.publication.{key}")
            for key in ("operation_id", "repo", "title", "body"):
                if not isinstance(publication.get(key), str) or not publication.get(key, "").strip():
                    _error(errors, "invalid_signal_publication", f"publication.{key} must be a non-empty string", f"signal.publication.{key}")

    if require_confirmed and lifecycle != "confirmed":
        _error(errors, "signal_not_confirmed", "Signal lifecycle must be confirmed", "signal.lifecycle")
    return {"valid": not errors, "errors": errors}


def validate_basis_signal(basis: dict[str, Any], mode: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    basis_kind = basis.get("kind")
    if mode == "discovery" and basis_kind not in {"signal", "discovery-evidence"}:
        _error(errors, "discovery_signal_required", "Discovery entries need a Signal or policy-permitted reproducible evidence", "basis.kind")
    if basis_kind not in {"signal", "discovery-evidence"}:
        return errors
    signal = basis.get("signal")
    if not isinstance(signal, dict):
        _error(errors, "missing_signal_record", "This basis needs a structured Signal 0.3 record", "basis.signal")
        return errors
    for error in validate_signal(signal)["errors"]:
        errors.append({**error, "path": error["path"].replace("signal", "basis.signal", 1)})
    if basis_kind == "discovery-evidence" and not (
        signal.get("record_type") == "local_evidence" and signal.get("claim_type") == "reproducible_evidence"
    ):
        _error(errors, "discovery_signal_shape_mismatch", "discovery-evidence requires local_evidence/reproducible_evidence", "basis.signal")
    return errors


def signal_readiness_blockers(basis: dict[str, Any], mode: str) -> list[dict[str, str]]:
    if mode not in {"issue-backed", "discovery"}:
        return []
    if mode == "discovery" and basis.get("kind") not in {"signal", "discovery-evidence"}:
        return [{"code": "discovery_signal_required", "message": "Discovery work needs a Signal.", "path": "basis.kind"}]
    if basis.get("kind") not in {"signal", "discovery-evidence"}:
        return []
    signal = basis.get("signal")
    if not isinstance(signal, dict):
        return [{"code": "missing_signal_record", "message": "No Signal 0.3 record is present.", "path": "basis.signal"}]
    if signal.get("lifecycle") in {"rejected", "expired"}:
        return [{"code": "signal_unavailable", "message": "The Signal was rejected or expired.", "path": "basis.signal.lifecycle"}]
    if signal.get("record_type") != "local_evidence":
        verification = signal.get("verification")
        if not isinstance(verification, dict) or verification.get("status") != "verified" or verification.get("reference") != signal.get("reference"):
            return [{"code": "signal_verification_required", "message": "An external Signal needs current public-record verification.", "path": "basis.signal.verification"}]
    return []
