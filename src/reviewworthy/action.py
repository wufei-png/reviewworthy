"""Read-only, deterministic checks suitable for a GitHub Action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .packet import validate_packet
from .util import read_json


def check_packet(path: Path, changed_files: list[str] | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {
            "conclusion": "success",
            "violations": [],
            "unknowns": [f"Contribution packet not found: {path}"],
            "checked": False,
            "mode": "read-only",
        }

    try:
        packet = read_json(path)
    except (OSError, ValueError) as exc:
        return {
            "conclusion": "failure",
            "violations": [{"code": "invalid_json", "message": str(exc)}],
            "unknowns": [],
            "checked": True,
            "mode": "read-only",
        }

    if not isinstance(packet, dict):
        return {
            "conclusion": "failure",
            "violations": [{"code": "invalid_packet", "message": "Contribution packet must be a JSON object."}],
            "unknowns": [],
            "checked": True,
            "mode": "read-only",
        }

    validation = validate_packet(packet)
    violations = list(validation["errors"])
    unknowns: list[str] = []

    policy = packet.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    if not policy:
        unknowns.append("Policy result is absent; Action does not infer permission.")
    elif not policy.get("authoritative_claims") or policy.get("posture") == "conservative":
        unknowns.append("Policy contains unknown claims; Action reports this without blocking by default.")

    if policy.get("conflicts"):
        violations.append({"code": "policy_conflict", "message": "Policy sources conflict."})

    diff_record = packet.get("diff", {})
    if not isinstance(diff_record, dict):
        diff_record = {}
    contract = packet.get("contract", {})
    if not isinstance(contract, dict):
        contract = {}
    provided_files = changed_files if changed_files is not None else diff_record.get("changed_files")
    scope = contract.get("scope", {})
    scoped_files = set(scope.get("files", [])) if isinstance(scope, dict) else set()
    if provided_files and scoped_files:
        extra = sorted(set(provided_files) - scoped_files)
        if extra:
            violations.append({"code": "out_of_scope_files", "message": f"Changed files are outside the approved scope: {extra}"})
    elif not provided_files:
        unknowns.append("Changed-file evidence was not provided; scope cannot be checked.")

    diff = diff_record
    budget = contract.get("max_diff_lines")
    if budget is not None and isinstance(diff, dict) and "additions" in diff and "deletions" in diff:
        changed_lines = int(diff.get("additions", 0)) + int(diff.get("deletions", 0))
        if changed_lines > int(budget):
            violations.append({"code": "diff_budget_exceeded", "message": f"Diff has {changed_lines} changed lines; budget is {budget}."})
    elif budget is not None:
        unknowns.append("Diff line counts are missing; the scope budget cannot be checked.")

    return {
        "conclusion": "failure" if violations else "success",
        "violations": violations,
        "unknowns": unknowns,
        "checked": True,
        "mode": "read-only",
    }
