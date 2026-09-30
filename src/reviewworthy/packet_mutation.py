"""Typed Packet mutations and shared evidence invalidation, without remote writes."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .packet import (
    issue_basis_blockers, policy_violations, require_current_packet,
    result_record, semantic_snapshot, skeleton_packet,
)
from .policy import inspect_policy
from .repository import parse_public_record, repository_identity, repository_matches
from .signal import require_current_signal, signal_readiness_blockers, validate_signal
from .util import atomic_write_json


def _set_result(packet: dict[str, Any], node: str, status: str, evidence: list[str] | None = None) -> None:
    records = packet["results"]
    records[:] = [record for record in records if record.get("node") != node]
    records.append(result_record(node, status, evidence))


def basis_errors(packet: dict[str, Any]) -> list[dict[str, str]]:
    """Check current basis evidence without checking later workflow stages."""

    basis = packet["basis"]
    errors = issue_basis_blockers(packet)
    errors.extend(signal_readiness_blockers(basis, packet["entry"]["mode"], packet["repository"]))
    if basis.get("kind") in {"signal", "discovery-evidence"}:
        errors.extend(validate_signal(basis.get("signal"), repository=packet["repository"])["errors"])
    if basis.get("kind") == "discovery-evidence" and packet["policy"].get("authoritative_claims", {}).get("discovery_evidence_allowed") is not True:
        errors.append({"code": "discovery_evidence_policy_unknown", "message": "Discovery evidence requires explicit policy allowance.", "path": "policy"})
    return errors


def maintain_packet(previous: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any]:
    """Maintain derived results and invalidate affected evidence on semantic changes.

    Completed understanding is reset explicitly; its old material hash is retained,
    never rebound to the new snapshot. Audit-only and identical updates are inert.
    """

    require_current_packet(previous)
    updated = deepcopy(updated)
    for name in ("repository", "entry", "basis", "contract", "policy", "review", "verification", "ownership", "snapshots", "understanding", "narrative"):
        if not isinstance(updated.get(name), dict):
            raise ValueError(f"packet.{name} must be an object")
    records = updated.get("results")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError("packet.results must be a list of result objects")
    if semantic_snapshot(previous) != semantic_snapshot(updated):
        basis_changed = any(previous.get(key) != updated.get(key) for key in ("entry", "candidate_selection"))
        # The semantic projection excludes provider timestamps.
        old_basis = deepcopy(updated)
        old_basis["basis"] = previous.get("basis")
        basis_changed = basis_changed or semantic_snapshot(old_basis) != semantic_snapshot(updated)
        contract_changed = previous.get("contract") != updated.get("contract")
        old_policy = deepcopy(updated)
        old_policy["policy"] = previous.get("policy")
        policy_changed = semantic_snapshot(old_policy) != semantic_snapshot(updated)
        if basis_changed or policy_changed:
            updated["contract"]["approval"] = {"status": "not_run", "human_confirmed": False}
        if basis_changed or contract_changed or policy_changed:
            updated["diff"] = skeleton_packet(updated["contribution_id"], "issue-backed")["diff"]
            _set_result(updated, "implementation", "not_run")
        updated["verification"]["receipts"] = []
        updated["ownership"]["status"] = "not_run"
        updated["narrative"]["final_preview_confirmed"] = False
        for node in ("verification", "ownership", "narrative"):
            _set_result(updated, node, "not_run")
        for phase in ("orientation", "assessment"):
            record = updated["understanding"].get(phase)
            if isinstance(record, dict):
                record["status"] = "not_run"
    policy_errors = policy_violations(updated, enforce_disclosure=False)
    policy_errors = [error for error in policy_errors if not error["path"].startswith("narrative")]
    policy_passed = any(record.get("node") == "policy_check" and record.get("status") == "passed" and record.get("evidence") for record in records)
    if updated["policy"].get("result") == "passed" or policy_passed:
        _set_result(updated, "policy_check", "blocked" if policy_errors else "passed", [] if policy_errors else ["packet.policy"])
    elif updated["policy"].get("result") == "blocked":
        _set_result(updated, "policy_check", "blocked")
    errors = basis_errors(updated)
    _set_result(updated, "contribution_basis", "blocked" if errors else "passed", [] if errors else ["packet.basis"])
    approval = updated["contract"].get("approval", {})
    if approval.get("status") != "approved" or approval.get("human_confirmed") is not True:
        _set_result(updated, "contribution_contract", "not_run")
    updated["snapshots"]["semantic"] = semantic_snapshot(updated)
    return updated


def replace_packet(path: Path, previous: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any]:
    """Validate mutation structure and atomically replace the single Packet file."""

    maintained = maintain_packet(previous, updated)
    atomic_write_json(path, maintained)
    return maintained


def bind_policy(packet: dict[str, Any], root: Path) -> dict[str, Any]:
    updated = deepcopy(packet)
    updated["policy"] = inspect_policy(root)
    return updated


def record_basis(packet: dict[str, Any], *, issue: str | None = None, signal: dict[str, Any] | None = None) -> dict[str, Any]:
    if (issue is None) == (signal is None):
        raise ValueError("Provide exactly one Issue URL or Signal artifact")
    updated = deepcopy(packet)
    parsed = parse_public_record(issue if issue is not None else signal.get("reference"))
    if issue is not None and (parsed is None or parsed["record_type"] != "issue"):
        raise ValueError("--issue requires a canonical public GitHub Issue URL")
    if parsed:
        slug = f"{parsed['owner']}/{parsed['name']}"
        repository = updated["repository"]
        if not repository.get("owner") and not repository.get("name"):
            updated["repository"] = repository_identity(slug)
        elif not repository_matches(repository, slug):
            raise ValueError("Contribution basis must belong to packet.repository")
    if issue is not None:
        # Re-recording the same Issue preserves its provider evidence.
        if packet["basis"].get("kind") == "issue" and packet["basis"].get("references") == [issue]:
            basis = deepcopy(packet["basis"])
        else:
            basis = {"kind": "issue", "references": [issue]}
        mode = "issue-backed"
    else:
        require_current_signal(signal)
        validation = validate_signal(signal, repository=updated["repository"])
        if not validation["valid"]:
            raise ValueError(f"Invalid Contribution Signal: {validation['errors']}")
        if signal.get("lifecycle") in {"rejected", "expired"}:
            raise ValueError("A rejected or expired Signal cannot be bound")
        basis = {"kind": "discovery-evidence" if signal["record_type"] == "local_evidence" else "signal", "signal": deepcopy(signal)}
        mode = "discovery"
    updated["basis"] = basis
    updated["entry"]["mode"] = mode
    # Keep candidate_selection, including advisory and duplicate-work gates.
    return updated
