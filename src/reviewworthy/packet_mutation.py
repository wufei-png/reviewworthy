"""Typed Packet mutations and shared evidence invalidation, without remote writes."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .contract import CONTRACT_FIELDS, contract_snapshot, validate_contract
from .git import verification_plan_digest
from .packet import (
    issue_basis_blockers, policy_violations, require_current_packet,
    readiness_blockers, result_record, semantic_snapshot, skeleton_packet, validate_packet,
)
from .policy import inspect_policy
from .repository import parse_public_record, repository_identity, repository_matches, validate_repository_identity
from .signal import require_current_signal, signal_readiness_blockers, validate_signal
from .util import atomic_write_json


def _set_result(packet: dict[str, Any], node: str, status: str, evidence: list[str] | None = None) -> None:
    records = packet["results"]
    records[:] = [record for record in records if record.get("node") != node]
    records.append(result_record(node, status, evidence))


def basis_errors(packet: dict[str, Any]) -> list[dict[str, str]]:
    """Check current basis evidence without checking later workflow stages."""

    basis = packet["basis"]
    errors = validate_repository_identity(packet["repository"])
    errors.extend(issue_basis_blockers(packet))
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
    if (approval.get("status") == "approved" and approval.get("human_confirmed") is True
            and approval.get("contract_sha256") == contract_snapshot(updated["contract"])):
        _set_result(updated, "contribution_contract", "passed", ["packet.contract.approval"])
    else:
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


def record_basis(packet: dict[str, Any], *, issue: str | None = None, signal: dict[str, Any] | None = None, repository: str | None = None) -> dict[str, Any]:
    if (issue is None) == (signal is None):
        raise ValueError("Provide exactly one Issue URL or Signal artifact")
    updated = deepcopy(packet)
    if repository is not None:
        identity = repository_identity(repository)
        current = updated["repository"]
        if not current.get("owner") and not current.get("name"):
            updated["repository"] = identity
        elif not repository_matches(current, repository):
            raise ValueError("Basis repository must match the established Packet identity")
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


def bind_contract(packet: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Embed existing Contract fields; approval belongs solely to the Packet."""

    allowed = {*CONTRACT_FIELDS, "contract_version", "contribution_id", "approval"}
    if set(contract) - allowed:
        raise ValueError("Contract input may contain only existing Contract fields")
    embedded = deepcopy(contract)
    embedded["approval"] = {"status": "not_run", "human_confirmed": False}
    validation = validate_contract(embedded)
    if not validation["valid"]:
        raise ValueError(f"Invalid Contribution Contract: {validation['errors']}")
    if embedded["contribution_id"] != packet["contribution_id"]:
        raise ValueError("Contract contribution_id must match packet.contribution_id")
    if contract_snapshot(embedded) == contract_snapshot(packet["contract"]):
        embedded["approval"] = deepcopy(packet["contract"].get("approval", embedded["approval"]))
    updated = deepcopy(packet)
    updated["contract"] = embedded
    return updated


def approval_errors(packet: dict[str, Any]) -> list[dict[str, str]]:
    """Require established policy, verified basis and candidate/hard-stop gates."""

    errors = basis_errors(packet)
    established = packet["policy"].get("result") == "passed" or any(
        record.get("node") == "policy_check" and record.get("status") == "passed" and record.get("evidence")
        for record in packet["results"]
    )
    if not established:
        errors.append({"code": "policy_not_bound", "message": "Bind repository policy before Contract approval.", "path": "policy"})
    errors.extend(error for error in policy_violations(packet, enforce_disclosure=False) if not error["path"].startswith("narrative"))
    errors.extend(error for error in readiness_blockers(packet) if error["path"].startswith("candidate_selection"))
    if packet["review"].get("hard_stops"):
        errors.append({"code": "hard_stop", "message": "Resolve independent hard stops before Contract approval.", "path": "review.hard_stops"})
    return errors


def approve_contract(packet: dict[str, Any], *, human_confirmed: bool) -> dict[str, Any]:
    if human_confirmed is not True:
        raise ValueError("Contract approval requires --human-confirmed")
    contract = deepcopy(packet["contract"])
    contract["approval"] = {"status": "not_run", "human_confirmed": False}
    validation = validate_contract(contract)
    errors = approval_errors(packet)
    if not validation["valid"] or errors:
        raise ValueError(f"Contract approval prerequisites unresolved: {validation['errors'] + errors}")
    if contract.get("contribution_id") != packet["contribution_id"]:
        raise ValueError("Contract contribution_id must match packet.contribution_id")
    updated = deepcopy(packet)
    updated["contract"]["approval"] = {
        "status": "approved", "human_confirmed": True,
        "contract_sha256": contract_snapshot(contract),
    }
    return updated


def record_review(packet: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    """Record an existing review section or risk-assessment result monotonically."""

    if "review_profile" in review:
        allowed = {"review_profile", "signals", "hard_stops", "user_escalated", "requested_review_profile", "changed_files", "heightened_path_globs", "matched_path_rules"}
        profile = review["review_profile"]
    else:
        allowed = {"profile", "signals", "hard_stops"}
        profile = review.get("profile")
    if set(review) - allowed:
        raise ValueError("Review input must be an existing review section or risk assess result")
    ranks = {"standard": 0, "heightened": 1, "learning": 2}
    if not isinstance(profile, str) or profile not in ranks:
        raise ValueError("Review profile must be standard, heightened, or learning")
    updated = deepcopy(packet)
    current = updated["review"]
    if current.get("profile") not in ranks:
        raise ValueError("Current Packet review profile is invalid")
    for key in ("signals", "hard_stops"):
        incoming = review.get(key, [])
        if not isinstance(incoming, list) or not all(isinstance(item, (str, dict)) for item in incoming):
            raise ValueError(f"review.{key} must be a list of existing risk records")
        current.setdefault(key, [])
        if not isinstance(current[key], list):
            raise ValueError(f"packet.review.{key} must be a list")
        for item in incoming:
            if item not in current[key]:
                current[key].append(deepcopy(item))
    current["profile"] = max((current["profile"], profile), key=ranks.__getitem__)
    if current["signals"] and current["profile"] == "standard":
        current["profile"] = "heightened"
    return updated


def record_verification_plan(packet: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Consume the current plan shape, computing the digest within the CLI."""

    if set(plan) != {"plan_version", "checks"}:
        raise ValueError("Verification input must contain only plan_version and checks")
    checks = plan.get("checks")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "argv", "cwd", "required"} for check in checks):
        raise ValueError("Each verification check must contain only id, argv, cwd and required")
    updated = deepcopy(packet)
    updated["verification"]["plan"] = deepcopy(plan)
    updated["verification"]["plan_digest"] = verification_plan_digest(plan)
    errors = [error for error in validate_packet(updated)["errors"] if error["path"].startswith("verification.plan")]
    if errors:
        raise ValueError(f"Invalid verification plan: {errors}")
    return updated
