"""Read-only, deterministic checks suitable for a GitHub Action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .packet import deterministic_evidence_checks, policy_violations, validate_packet
from .policy import CLAIM_KEYS
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
    evidence_violations, evidence_unknowns = deterministic_evidence_checks(packet, changed_files)
    violations.extend(evidence_violations)
    unknowns.extend(evidence_unknowns)

    return {
        "conclusion": "failure" if violations else "success",
        "violations": violations,
        "unknowns": unknowns,
        "checked": True,
        "mode": "read-only",
    }
