"""Policy-aware AI-assistance records and disclosure rendering."""

from __future__ import annotations

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


def _as_disclosure_record(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"text": value, "locations": ["pr_body"], "human_confirmed": bool(value.strip())}
    return value if isinstance(value, dict) else {}


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
    if not requirements["required"]:
        return []
    assistance = packet.get("ai_assistance", {})
    narrative = packet.get("narrative", {})
    raw_record = assistance.get("disclosure") if isinstance(assistance, dict) and "disclosure" in assistance else narrative.get("ai_disclosure") if isinstance(narrative, dict) else None
    record = _as_disclosure_record(raw_record)
    errors: list[dict[str, str]] = []
    text = record.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append({"code": "missing_ai_disclosure", "message": "AI-assistance disclosure text is required.", "path": "narrative.ai_disclosure.text"})
    locations = record.get("locations", [])
    if not isinstance(locations, list):
        locations = []
    invalid_locations = sorted(set(str(value) for value in locations) - DISCLOSURE_LOCATIONS)
    if invalid_locations:
        errors.append({"code": "invalid_disclosure_location", "message": f"Unsupported disclosure location(s): {invalid_locations}", "path": "narrative.ai_disclosure.locations"})
    missing_locations = sorted(set(requirements["locations"]) - set(locations))
    if missing_locations:
        errors.append({"code": "missing_disclosure_location", "message": f"Disclosure must record these location(s): {missing_locations}", "path": "narrative.ai_disclosure.locations"})
    if record.get("human_confirmed") is not True:
        errors.append({"code": "disclosure_not_human_confirmed", "message": "The contributor must confirm the disclosure record.", "path": "narrative.ai_disclosure.human_confirmed"})

    assistance = packet.get("ai_assistance", {})
    stages = assistance.get("stages", []) if isinstance(assistance, dict) else []
    if not isinstance(stages, list):
        stages = []
    stage_names = {stage.get("name") for stage in stages if isinstance(stage, dict)}
    missing_stages = sorted(set(requirements["stages"]) - stage_names)
    if missing_stages:
        errors.append({"code": "missing_disclosure_stage", "message": f"AI-assistance stages are missing: {missing_stages}", "path": "ai_assistance.stages"})
    return errors


def render_disclosure(packet: dict[str, Any], location: str | None = None) -> dict[str, Any]:
    policy = packet.get("policy", {})
    requirements = disclosure_requirements(policy if isinstance(policy, dict) else {})
    assistance = packet.get("ai_assistance", {})
    narrative = packet.get("narrative", {})
    raw_record = assistance.get("disclosure") if isinstance(assistance, dict) and "disclosure" in assistance else narrative.get("ai_disclosure") if isinstance(narrative, dict) else None
    record = _as_disclosure_record(raw_record)
    stages = assistance.get("stages", []) if isinstance(assistance, dict) else []
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
        text = f"AI assistance was used during {stage_text}. The contributor reviewed and verified the resulting contribution."
    return {
        "required": requirements["required"],
        "location": selected_location,
        "allowed_locations": requirements["locations"],
        "required_stages": requirements["stages"],
        "text": text,
    }
