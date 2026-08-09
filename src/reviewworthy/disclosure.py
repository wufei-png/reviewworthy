"""Policy-aware AI-assistance records and disclosure rendering."""

from __future__ import annotations

import re
from typing import Any


DISCLOSURE_LOCATIONS = {"pr_body", "commit_message", "commit_trailer", "issue_body", "checklist", "other"}
DISCLOSURE_STAGES = {
    "repository_orientation",
    "candidate_triage",
    "design",
    "implementation",
    "verification",
    "narrative",
    "review_response",
}
ASSISTANCE_LEVELS = {"assisted", "generated", "reviewed"}
_VERIFICATION_CLAIM_RE = re.compile(r"\b(reviewed|verified|validated|confirmed)\b", re.IGNORECASE)


def disclosure_requirements(policy: dict[str, Any]) -> dict[str, Any]:
    claims = policy.get("authoritative_claims", {}) if isinstance(policy, dict) else {}
    if not isinstance(claims, dict):
        claims = {}
    posture = policy.get("posture") if isinstance(policy, dict) else "conservative"
    required = claims.get("disclosure_required") is not False or posture != "explicit"
    locations = claims.get("disclosure_locations")
    stages = claims.get("disclosure_stages")
    if not isinstance(locations, list) or not locations:
        locations = ["pr_body"] if required else []
    if not isinstance(stages, list):
        stages = []
    return {"required": required, "locations": locations, "stages": stages}


def disclosure_errors(packet: dict[str, Any]) -> list[dict[str, str]]:
    policy = packet.get("policy", {})
    requirements = disclosure_requirements(policy if isinstance(policy, dict) else {})
    assistance = packet.get("ai_assistance", {})
    if isinstance(assistance, dict) and assistance.get("used") is False:
        return []
    if not requirements["required"]:
        return []
    record = assistance.get("disclosure") if isinstance(assistance, dict) and isinstance(assistance.get("disclosure"), dict) else {}
    errors: list[dict[str, str]] = []
    text = record.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append({"code": "missing_ai_disclosure", "message": "AI-assistance disclosure text is required.", "path": "ai_assistance.disclosure.text"})
    locations = record.get("locations", [])
    if not isinstance(locations, list):
        locations = []
    invalid_locations = sorted(set(str(value) for value in locations) - DISCLOSURE_LOCATIONS)
    if invalid_locations:
        errors.append({"code": "invalid_disclosure_location", "message": f"Unsupported disclosure location(s): {invalid_locations}", "path": "ai_assistance.disclosure.locations"})
    missing_locations = sorted(set(requirements["locations"]) - set(locations))
    if missing_locations:
        errors.append({"code": "missing_disclosure_location", "message": f"Disclosure must record these location(s): {missing_locations}", "path": "ai_assistance.disclosure.locations"})
    disallowed_locations = sorted(set(locations) - set(requirements["locations"]))
    if disallowed_locations:
        errors.append({"code": "disallowed_disclosure_location", "message": f"Disclosure records locations not allowed by policy: {disallowed_locations}", "path": "ai_assistance.disclosure.locations"})
    if record.get("human_confirmed") is not True:
        errors.append({"code": "disclosure_not_human_confirmed", "message": "The contributor must confirm the disclosure record.", "path": "ai_assistance.disclosure.human_confirmed"})

    assistance = packet.get("ai_assistance", {})
    stages = assistance.get("stages", []) if isinstance(assistance, dict) else []
    if not isinstance(stages, list):
        stages = []
    stage_names = {stage.get("name") for stage in stages if isinstance(stage, dict)}
    missing_stages = sorted(set(requirements["stages"]) - stage_names)
    if missing_stages:
        errors.append({"code": "missing_disclosure_stage", "message": f"AI-assistance stages are missing: {missing_stages}", "path": "ai_assistance.stages"})
    required_stage_names = set(requirements["stages"]) or stage_names
    unverified = [
        stage for stage in stages
        if isinstance(stage, dict) and stage.get("name") in required_stage_names and stage.get("human_verified") is not True
    ]
    if unverified and isinstance(text, str) and _VERIFICATION_CLAIM_RE.search(text):
        errors.append({"code": "disclosure_overclaims_verification", "message": "Disclosure cannot claim reviewed or verified work while a required AI-assistance stage is not human_verified.", "path": "ai_assistance.disclosure.text"})
    if "pr_body" in locations:
        narrative = packet.get("narrative", {})
        body = narrative.get("body", "") if isinstance(narrative, dict) else ""
        if not isinstance(body, str) or text not in body:
            errors.append({"code": "disclosure_not_in_pr_body", "message": "Disclosure text recorded for pr_body must appear exactly in the final PR Body.", "path": "narrative.body"})
    return errors


def render_disclosure(packet: dict[str, Any], location: str | None = None) -> dict[str, Any]:
    policy = packet.get("policy", {})
    requirements = disclosure_requirements(policy if isinstance(policy, dict) else {})
    assistance = packet.get("ai_assistance", {})
    if isinstance(assistance, dict) and assistance.get("used") is False:
        return {
            "required": False,
            "location": None,
            "allowed_locations": requirements["locations"],
            "required_stages": requirements["stages"],
            "text": "",
        }
    if not isinstance(assistance, dict) or not isinstance(assistance.get("disclosure"), dict):
        raise ValueError("Packet 0.3 disclosure must be recorded at ai_assistance.disclosure")
    record = assistance.get("disclosure") if isinstance(assistance, dict) and isinstance(assistance.get("disclosure"), dict) else {}
    stages = assistance.get("stages", []) if isinstance(assistance, dict) else []
    if location is not None and location not in requirements["locations"]:
        raise ValueError(f"Disclosure location is not allowed by policy: {location}")
    if not requirements["required"] and not requirements["locations"]:
        return {
            "required": False,
            "location": None,
            "allowed_locations": [],
            "required_stages": requirements["stages"],
            "text": "",
        }
    selected_location = location or (requirements["locations"][0] if requirements["locations"] else "pr_body")
    if selected_location not in DISCLOSURE_LOCATIONS:
        raise ValueError(f"Unsupported disclosure location: {selected_location}")
    stage_text = ", ".join(
        str(stage.get("name"))
        for stage in stages
        if isinstance(stage, dict) and stage.get("name")
    ) or "the recorded contribution workflow"
    text = str(record.get("text", "")).strip()
    if not text:
        required_stage_names = set(requirements["stages"]) or {
            stage.get("name") for stage in stages if isinstance(stage, dict) and stage.get("name")
        }
        related_stages = [
            stage for stage in stages
            if isinstance(stage, dict) and stage.get("name") in required_stage_names
        ]
        all_verified = bool(related_stages) and all(stage.get("human_verified") is True for stage in related_stages)
        suffix = "The contributor reviewed and verified the resulting contribution." if all_verified else "Manual verification of the resulting contribution is incomplete."
        text = f"AI assistance was used during {stage_text}. {suffix}"
    return {
        "required": requirements["required"],
        "location": selected_location,
        "allowed_locations": requirements["locations"],
        "required_stages": requirements["stages"],
        "text": text,
    }
