"""Standalone Contribution Contract artifact and renderer."""

from __future__ import annotations

from typing import Any

from .util import sha256_json


CONTRACT_VERSION = "0.1"
CONTRACT_FIELDS = (
    "problem",
    "non_goals",
    "scope",
    "invariants",
    "design",
    "alternatives",
    "validation_plan",
    "risks",
    "success_criteria",
    "max_diff_lines",
)


def contract_snapshot(contract: dict[str, Any]) -> str:
    """Hash the approved contract fields, excluding the approval record itself."""

    return sha256_json({key: contract.get(key) for key in CONTRACT_FIELDS})


def skeleton_contract(contribution_id: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "contribution_id": contribution_id,
        "problem": "",
        "non_goals": [],
        "scope": {"files": [], "modules": []},
        "invariants": [],
        "design": "",
        "alternatives": [],
        "validation_plan": [],
        "risks": [],
        "success_criteria": [],
        "max_diff_lines": 400,
        "approval": {"status": "not_run", "human_confirmed": False},
    }


def validate_contract(contract: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    def error(code: str, message: str, path: str) -> None:
        errors.append({"code": code, "message": message, "path": path})

    if contract.get("contract_version") != CONTRACT_VERSION:
        error("unsupported_version", "contract_version must be 0.1", "contract_version")
    if not isinstance(contract.get("contribution_id"), str) or not contract.get("contribution_id", "").strip():
        error("missing_contribution_id", "contribution_id is required", "contribution_id")
    for key in ("problem", "design"):
        if not isinstance(contract.get(key), str) or not contract.get(key, "").strip():
            error("empty_contract_text", f"{key} must be explained before approval", key)
    for key in CONTRACT_FIELDS:
        if key not in contract:
            error("missing_contract_field", f"Contract field is required: {key}", key)
    for key in ("non_goals", "invariants", "validation_plan", "risks", "success_criteria"):
        if key in contract and not isinstance(contract[key], list):
            error("invalid_contract_list", f"{key} must be a list", key)
    scope = contract.get("scope")
    if not isinstance(scope, dict):
        error("invalid_scope", "scope must be an object", "scope")
    else:
        for key in ("files", "modules"):
            if key in scope and not isinstance(scope[key], list):
                error("invalid_scope_list", f"scope.{key} must be a list", f"scope.{key}")
            elif key in scope and not all(isinstance(item, str) for item in scope[key]):
                error("invalid_scope_item", f"scope.{key} items must be strings", f"scope.{key}")
        if not scope.get("files") and not scope.get("modules"):
            error("empty_scope", "At least one file or module must be bounded", "scope")
    if not isinstance(contract.get("alternatives"), list):
        error("invalid_alternatives", "alternatives must be a list", "alternatives")
    if not isinstance(contract.get("max_diff_lines"), int) or isinstance(contract.get("max_diff_lines"), bool) or contract.get("max_diff_lines", 0) <= 0:
        error("invalid_diff_budget", "max_diff_lines must be a positive integer", "max_diff_lines")
    approval = contract.get("approval")
    if approval is not None and not isinstance(approval, dict):
        error("invalid_approval", "approval must be an object", "approval")
    elif isinstance(approval, dict):
        if approval.get("status") not in {"not_run", "approved", "rejected"}:
            error("invalid_approval_status", "approval.status must be not_run, approved, or rejected", "approval.status")
        if not isinstance(approval.get("human_confirmed"), bool):
            error("invalid_approval_confirmation", "approval.human_confirmed must be boolean", "approval.human_confirmed")
        if approval.get("status") == "approved":
            if not isinstance(approval.get("contract_sha256"), str) or not approval.get("contract_sha256", "").strip():
                error("missing_approval_snapshot", "An approved contract needs contract_sha256", "approval.contract_sha256")
            elif approval.get("contract_sha256") != contract_snapshot(contract):
                error("stale_contract_approval", "Contract approval does not match the current contract fields", "approval.contract_sha256")
    return {"valid": not errors, "errors": errors}


def render_contract(contract: dict[str, Any]) -> str:
    validation = validate_contract(contract)
    if not validation["valid"]:
        raise ValueError(f"Cannot render invalid contribution contract: {validation['errors']}")
    scope = contract["scope"]
    lines = [
        "# Contribution contract",
        "",
        f"- Contribution: `{contract['contribution_id']}`",
        f"- Diff budget: `{contract['max_diff_lines']}` changed lines",
        "",
        "## Problem",
        "",
        contract["problem"],
        "",
        "## Non-goals",
        "",
    ]
    lines.extend(f"- {item}" for item in contract["non_goals"])
    lines.extend(["", "## Scope", "", "Files: " + (", ".join(f"`{item}`" for item in scope.get("files", [])) or "not yet bounded")])
    lines.append("Modules: " + (", ".join(f"`{item}`" for item in scope.get("modules", [])) or "not yet bounded"))
    lines.extend(["", "## Invariants", ""])
    lines.extend(f"- {item}" for item in contract["invariants"])
    lines.extend(["", "## Design", "", contract["design"], "", "## Alternatives", ""])
    for alternative in contract["alternatives"]:
        if isinstance(alternative, dict):
            lines.append(f"- **{alternative.get('option', 'Alternative')}** — {alternative.get('rejected_because', '')}")
        else:
            lines.append(f"- {alternative}")
    lines.extend(["", "## Validation plan", ""])
    lines.extend(f"- {item}" for item in contract["validation_plan"])
    lines.extend(["", "## Risks", ""])
    lines.extend(f"- {item}" for item in contract["risks"])
    lines.extend(["", "## Success criteria", ""])
    lines.extend(f"- {item}" for item in contract["success_criteria"])
    lines.append("")
    return "\n".join(lines)
