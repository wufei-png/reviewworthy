"""Retryable Issue-backed entry using existing Git-private domain artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .brief import build_project_brief, validate_project_brief
from .git import local_state_path
from .packet import issue_reference, require_contribution_id, require_current_packet, skeleton_packet
from .packet_mutation import bind_policy, maintain_packet, record_basis
from .repository import parse_public_record, repository_matches
from .util import atomic_write_json, read_json


def prepare_start(root: Path, contribution_id: str, issue: str, focus: list[str]) -> dict[str, Any]:
    """Create absent artifacts only; retain bound decisions and contributor prose."""

    root = root.resolve()
    require_contribution_id(contribution_id)
    parsed = parse_public_record(issue)
    if not parsed or parsed["record_type"] != "issue":
        raise ValueError("start --issue requires a canonical public GitHub Issue URL")
    issue = parsed["url"]
    slug = f"{parsed['owner']}/{parsed['name']}"
    directory = local_state_path(root, f"reviewworthy/v0.3/contributions/{contribution_id}")
    packet_path = directory / "packet.json"
    brief_path = directory / "project-brief.json"
    current_brief = build_project_brief(root, focus)
    facts = current_brief["repository"]
    if facts["provider"] == "github" and not repository_matches(facts, slug):
        raise ValueError("The Issue must belong to the checkout's origin repository")

    if brief_path.exists():
        brief = read_json(brief_path)
        if not isinstance(brief, dict) or not validate_project_brief(brief)["valid"]:
            raise ValueError(f"Repair the existing Brief before retrying start: {brief_path}")
        if focus and brief["focus"] != focus:
            raise ValueError("start preserves existing focus; choose another contribution ID or explicitly regenerate the Brief")
    else:
        brief = current_brief

    reused = packet_path.exists()
    if reused:
        packet = require_current_packet(read_json(packet_path))
        if packet.get("contribution_id") != contribution_id:
            raise ValueError("Existing Packet contribution_id does not match start")
        if not repository_matches(packet.get("repository"), slug) or issue_reference(packet) != issue:
            raise ValueError("start preserves the existing Packet basis; use typed Packet operations to change it")
    else:
        packet = skeleton_packet(contribution_id, "issue-backed", slug)
        packet["repository"].update(default_branch=facts["default_branch"], base_sha=facts["base_sha"])
        packet = maintain_packet(packet, record_basis(bind_policy(packet, root), issue=issue))

    # Validate everything before writing; an interruption between these atomic
    # writes leaves a reusable Brief and no partly initialized Packet.
    if not brief_path.exists():
        atomic_write_json(brief_path, brief)
    if not reused:
        atomic_write_json(packet_path, packet)
    return {"packet": str(packet_path), "brief": str(brief_path), "reused_packet": reused,
            "brief_validation": validate_project_brief(brief, root)}
