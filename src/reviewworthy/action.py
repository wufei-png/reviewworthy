"""Read-only, deterministic checks suitable for a GitHub Action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .packet import deterministic_evidence_checks, policy_violations, validate_packet
from .policy import CLAIM_KEYS
from .util import read_json


ACTION_MODES = {"report", "enforce"}


def check_packet(
    path: Path,
    changed_files: list[str] | None = None,
    *,
    current_diff_available: bool | None = None,
    mode: str = "report",
    require_packet: bool = False,
    fail_on_unknown: bool = False,
    require_current_diff: bool = False,
) -> dict[str, Any]:
    """Check a packet in report mode, or opt into explicit enforcement.

    Report mode preserves the original read-only, non-blocking behavior for
    missing packets and unknown evidence. Enforce mode turns all three
    explicit requirements on; callers may also opt into individual
    requirements while remaining in report mode.
    """

    if mode not in ACTION_MODES:
        raise ValueError(f"mode must be one of {sorted(ACTION_MODES)}")
    enforce = mode == "enforce"
    require_packet = require_packet or enforce
    fail_on_unknown = fail_on_unknown or enforce
    require_current_diff = require_current_diff or enforce
    has_current_diff = changed_files is not None if current_diff_available is None else current_diff_available
    evidence_files = changed_files if current_diff_available is not False else []

    requirements = {
        "require_packet": require_packet,
        "fail_on_unknown": fail_on_unknown,
        "require_current_diff": require_current_diff,
    }
    if not path.is_file():
        violations = []
        if require_packet:
            violations.append({"code": "packet_required", "message": f"Contribution packet is required: {path}", "path": str(path)})
        return {
            "conclusion": "failure" if violations else "success",
            "violations": violations,
            "unknowns": [f"Contribution packet not found: {path}"],
            "checked": False,
            "mode": mode,
            "requirements": requirements,
        }

    try:
        packet = read_json(path)
    except (OSError, ValueError) as exc:
        return {
            "conclusion": "failure",
            "violations": [{"code": "invalid_json", "message": str(exc)}],
            "unknowns": [],
            "checked": True,
            "mode": mode,
            "requirements": requirements,
        }

    if not isinstance(packet, dict):
        return {
            "conclusion": "failure",
            "violations": [{"code": "invalid_packet", "message": "Contribution packet must be a JSON object."}],
            "unknowns": [],
            "checked": True,
            "mode": mode,
            "requirements": requirements,
        }

    validation = validate_packet(packet)
    violations = list(validation["errors"])
    unknowns: list[str] = []

    policy = packet.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    claims = policy.get("authoritative_claims", {})
    policy_complete = isinstance(claims, dict) and all(key in claims and claims[key] is not None for key in CLAIM_KEYS)
    if not policy:
        unknowns.append("Policy result is absent; Action does not infer permission.")
    elif not policy.get("authoritative_claims") or policy.get("posture") == "conservative":
        unknowns.append("Policy contains unknown claims; Action reports this without blocking by default.")
    else:
        missing_claims = sorted(key for key in CLAIM_KEYS if not isinstance(claims, dict) or claims.get(key) is None)
        if missing_claims:
            unknowns.append(f"Policy claims are incomplete; Action cannot infer missing claims: {missing_claims}.")

    violations.extend(policy_violations(packet, enforce_disclosure=policy.get("posture") == "explicit" and policy_complete))
    evidence_violations, evidence_unknowns = deterministic_evidence_checks(packet, evidence_files, strict=fail_on_unknown)
    violations.extend(evidence_violations)
    unknowns.extend(evidence_unknowns)

    if require_current_diff and not has_current_diff:
        violations.append(
            {
                "code": "current_diff_required",
                "message": "Current changed-file evidence is required; packet-declared files are not sufficient.",
                "path": "diff.changed_files",
            }
        )
    if fail_on_unknown:
        for message in unknowns:
            code = "unknown_policy" if message.startswith("Policy") else "unknown_evidence"
            path_value = "policy" if code == "unknown_policy" else "diff"
            violations.append({"code": code, "message": message, "path": path_value})

    return {
        "conclusion": "failure" if violations else "success",
        "violations": violations,
        "unknowns": unknowns,
        "checked": True,
        "mode": mode,
        "requirements": requirements,
    }
