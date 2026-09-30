"""Typed Packet mutations and shared evidence invalidation, without remote writes."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .contract import CONTRACT_FIELDS, contract_snapshot, validate_contract
from .disclosure import disclosure_errors
from .git import verification_plan_digest
from .packet import (
    current_verification_receipts, deterministic_evidence_checks, issue_basis_blockers, policy_violations, require_current_packet,
    readiness_blockers, result_record, semantic_snapshot, skeleton_packet, validate_packet,
)
from .policy import inspect_policy
from .repository import parse_public_record, repository_identity, repository_matches, validate_repository_identity
from .signal import require_current_signal, signal_readiness_blockers, validate_signal
from .util import atomic_write_json


def _set_result(packet: dict[str, Any], node: str, status: str, evidence: list[str] | None = None) -> None:
    records = packet["results"]
    replacement = result_record(node, status, evidence)
    position = next((index for index, record in enumerate(records) if record.get("node") == node), len(records))
    records[:] = [record for record in records if record.get("node") != node]
    records.insert(position, replacement)


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


def synchronize_verification_result(packet: dict[str, Any]) -> None:
    """Derive the flow result from required checks and exact current receipts."""

    verification = packet["verification"]
    required = {check["id"] for check in verification["plan"].get("checks", [])
                if isinstance(check, dict) and check.get("required") is True}
    receipts = verification.get("receipts", [])
    passing = {receipt["check_id"] for receipt in current_verification_receipts(packet)}
    errors = [error for error in validate_packet(packet)["errors"] if error["path"].startswith("verification")]
    if errors or any(receipt.get("integrity_status") != "stable" for receipt in receipts):
        status = "blocked"
    elif any(receipt.get("check_id") in required and receipt.get("command_outcome") == "failed" for receipt in receipts):
        status = "failed"
    elif required and required <= passing:
        status = "passed"
    else:
        status = "not_run"
    evidence = [f"packet.verification.receipts:{check_id}" for check_id in sorted(required & passing)]
    _set_result(packet, "verification", status, evidence)


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
    def changed_section(name: str) -> bool:
        old = deepcopy(updated)
        old[name] = previous.get(name, {})
        return semantic_snapshot(old) != semantic_snapshot(updated)

    basis_changed = any(changed_section(key) for key in ("entry", "basis", "candidate_selection"))
    policy_changed = changed_section("policy")
    contract_changed = changed_section("contract")
    if basis_changed or policy_changed:
        updated["contract"]["approval"] = {"status": "not_run", "human_confirmed": False}
    if basis_changed or policy_changed or contract_changed:
        updated["diff"] = skeleton_packet(updated["contribution_id"], "issue-backed")["diff"]
        _set_result(updated, "implementation", "not_run")
    verification_inputs_changed = (
        basis_changed or policy_changed or contract_changed
        or changed_section("diff") or changed_section("review")
        or previous["verification"].get("plan") != updated["verification"].get("plan")
        or previous["verification"].get("plan_digest") != updated["verification"].get("plan_digest")
    )
    if verification_inputs_changed:
        updated["verification"]["receipts"] = []
    if verification_inputs_changed or changed_section("verification"):
        updated["ownership"]["status"] = "not_run"
        _set_result(updated, "ownership", "not_run")
    if semantic_snapshot(previous) != semantic_snapshot(updated):
        updated["narrative"]["final_preview_confirmed"] = False
        _set_result(updated, "narrative", "not_run")
        for phase in ("orientation", "assessment"):
            record = updated["understanding"].get(phase)
            if isinstance(record, dict):
                record["status"] = "not_run"

    diff = updated.get("diff", {})
    diff_errors = [error for error in validate_packet(updated)["errors"] if error["path"].startswith("diff")]
    violations, _ = deterministic_evidence_checks(updated, strict=True)
    if diff.get("subject_digest") and diff.get("head_sha") and not diff_errors and not violations:
        _set_result(updated, "implementation", "passed", [
            f"Bound merge-base Diff {diff['subject_digest']} at head {diff['head_sha']}."
        ])
    else:
        _set_result(updated, "implementation", "not_run")
    synchronize_verification_result(updated)
    ownership_errors = [error for error in validate_packet(updated)["errors"] if error["path"].startswith("ownership")]
    ownership_status = updated["ownership"].get("status", "not_run")
    _set_result(updated, "ownership", "blocked" if ownership_errors else ownership_status,
                ["packet.ownership"] if ownership_status == "passed" and not ownership_errors else [])
    if verification_inputs_changed or changed_section("verification"):
        for stage in updated["ai_assistance"].get("stages", []):
            stage["human_verified"] = False
        updated["ai_assistance"]["disclosure"]["human_confirmed"] = False
    if previous.get("ai_assistance") != updated.get("ai_assistance"):
        updated["narrative"]["final_preview_confirmed"] = False
        _set_result(updated, "narrative", "not_run")
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
        verification = signal.get("verification")
        if (signal["record_type"] != "local_evidence" and isinstance(verification, dict)
                and updated["repository"].get("repository_id") is None):
            updated["repository"]["repository_id"] = verification["repository_id"]
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
        if key not in current and not incoming:
            continue
        current.setdefault(key, [])
        if not isinstance(current[key], list):
            raise ValueError(f"packet.review.{key} must be a list")
        for item in incoming:
            if item not in current[key]:
                current[key].append(deepcopy(item))
    current["profile"] = max((current["profile"], profile), key=ranks.__getitem__)
    if current.get("signals") and current["profile"] == "standard":
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


def record_ownership(packet: dict[str, Any], ownership: dict[str, Any]) -> dict[str, Any]:
    """Record the human/Skill check outcome, checking content and current evidence."""

    if set(ownership) != {"status", "problem", "scope", "verification", "risks"}:
        raise ValueError("Ownership input must contain status, problem, scope, verification and risks")
    updated = deepcopy(packet)
    updated["ownership"] = deepcopy(ownership)
    errors = [error for error in validate_packet(updated)["errors"] if error["path"].startswith("ownership")]
    if errors:
        raise ValueError(f"Invalid Ownership Check: {errors}")
    if ownership["status"] == "passed":
        current = maintain_packet(packet, packet)
        required_nodes = {"policy_check", "contribution_basis", "contribution_contract", "implementation", "verification"}
        incomplete = [record["node"] for record in current["results"]
                      if record["node"] in required_nodes and (record["status"] != "passed" or not record.get("evidence"))]
        errors = approval_errors(packet)
        if incomplete or errors:
            raise ValueError(f"Ownership requires current approved implementation and verification: {incomplete}, {errors}")
    return updated


def record_ai(packet: dict[str, Any], assistance: dict[str, Any]) -> dict[str, Any]:
    """Preserve explicit stage claims; changed disclosure requires fresh confirmation."""

    if set(assistance) != {"used", "stages", "disclosure"}:
        raise ValueError("AI input must contain only used, stages and disclosure")
    stages = assistance.get("stages")
    disclosure = assistance.get("disclosure")
    if (not isinstance(stages, list) or any(not isinstance(stage, dict)
            or set(stage) != {"name", "level", "human_verified"} for stage in stages)):
        raise ValueError("AI stages must contain name, level and human_verified")
    if not isinstance(disclosure, dict) or set(disclosure) != {"text", "locations", "human_confirmed"}:
        raise ValueError("Disclosure must contain text, locations and human_confirmed")
    if not isinstance(disclosure["locations"], list) or not all(isinstance(item, str) for item in disclosure["locations"]):
        raise ValueError("Disclosure locations must be strings")
    updated = deepcopy(packet)
    updated["ai_assistance"] = deepcopy(assistance)
    errors = [error for error in validate_packet(updated)["errors"] if error["path"].startswith("ai_assistance")]
    if errors:
        raise ValueError(f"Invalid AI-assistance record: {errors}")
    policy_errors = [error for error in disclosure_errors(updated)
                     if error["code"] not in {"disclosure_not_human_confirmed", "disclosure_not_in_pr_body"}]
    if policy_errors:
        raise ValueError(f"AI disclosure policy unresolved: {policy_errors}")
    old = packet["ai_assistance"]
    # A changed claim cannot carry confirmation from the prior disclosure.
    old_unconfirmed, new_unconfirmed = deepcopy(old), deepcopy(assistance)
    old_unconfirmed["disclosure"]["human_confirmed"] = False
    new_unconfirmed["disclosure"]["human_confirmed"] = False
    if old_unconfirmed != new_unconfirmed:
        updated["ai_assistance"]["disclosure"]["human_confirmed"] = False
    return updated
