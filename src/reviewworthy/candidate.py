"""Evidence-first candidate-menu validation and rendering."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .repository import parse_repository_slug, repository_identity, repository_matches
from .signal import validate_signal
from .util import sha256_json

MENU_VERSION = "0.1"
REVIEW_COSTS = {"small", "medium", "large", "unknown"}
VERIFIABILITY = {"high", "medium", "low", "unknown"}
RECOMMENDATIONS = {"plan_directly", "seek_maintainer_signal", "issue_only", "do_not_contribute"}


def skeleton_menu(repository: str) -> dict[str, Any]:
    return {
        "menu_version": MENU_VERSION,
        "repository": repository,
        "project_brief": "",
        "candidates": [],
        "selection": {"selected_id": "", "confirmed": False},
    }


def _error(errors: list[dict[str, str]], code: str, message: str, path: str) -> None:
    errors.append({"code": code, "message": message, "path": path})


def _candidate_by_id(menu: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in menu.get("candidates", []):
        if isinstance(candidate, dict) and candidate.get("id") == candidate_id:
            return candidate
    raise ValueError(f"Candidate is not present in the menu: {candidate_id}")


def validate_candidate_menu(menu: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if menu.get("menu_version") != MENU_VERSION:
        _error(errors, "unsupported_version", "menu_version must be 0.1", "menu_version")
    if not isinstance(menu.get("repository"), str) or not menu.get("repository", "").strip():
        _error(errors, "missing_repository", "repository is required", "repository")
    else:
        try:
            parse_repository_slug(menu["repository"])
        except ValueError:
            _error(errors, "invalid_repository", "repository must use the owner/name form", "repository")
    candidates = menu.get("candidates")
    if not isinstance(candidates, list):
        _error(errors, "invalid_candidates", "candidates must be a list", "candidates")
        candidates = []
    seen: set[str] = set()
    required = ("id", "title", "basis", "duplicate_search", "value", "scope", "review_cost", "verifiability", "risk", "recommendation")
    for index, candidate in enumerate(candidates):
        path = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            _error(errors, "invalid_candidate", "Each candidate must be an object", path)
            continue
        for key in required:
            if key not in candidate:
                _error(errors, "missing_candidate_field", f"Candidate field is required: {key}", f"{path}.{key}")
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            _error(errors, "invalid_candidate_id", "Candidate id must be non-empty", f"{path}.id")
        elif candidate_id in seen:
            _error(errors, "duplicate_candidate_id", f"Candidate id is duplicated: {candidate_id}", f"{path}.id")
        else:
            seen.add(candidate_id)
        if not isinstance(candidate.get("title"), str) or not candidate.get("title", "").strip():
            _error(errors, "invalid_candidate_title", "Candidate title must be non-empty", f"{path}.title")
        if "score" in candidate or "confidence" in candidate:
            _error(errors, "numeric_score_not_allowed", "Candidate menus use evidence fields, not a single AI score", path)
        if candidate.get("review_cost") not in REVIEW_COSTS:
            _error(errors, "invalid_review_cost", f"review_cost must be one of {sorted(REVIEW_COSTS)}", f"{path}.review_cost")
        if candidate.get("verifiability") not in VERIFIABILITY:
            _error(errors, "invalid_verifiability", f"verifiability must be one of {sorted(VERIFIABILITY)}", f"{path}.verifiability")
        if candidate.get("recommendation") not in RECOMMENDATIONS:
            _error(errors, "invalid_recommendation", f"recommendation must be one of {sorted(RECOMMENDATIONS)}", f"{path}.recommendation")
        if not isinstance(candidate.get("value"), dict):
            _error(errors, "invalid_value", "value must be an object", f"{path}.value")
        if not isinstance(candidate.get("scope"), dict):
            _error(errors, "invalid_candidate_scope", "scope must be an object", f"{path}.scope")
        basis = candidate.get("basis")
        if not isinstance(basis, dict) or basis.get("kind") not in {"issue", "signal", "discovery-evidence"}:
            _error(errors, "invalid_candidate_basis", "basis.kind must be issue, signal, or discovery-evidence", f"{path}.basis")
        elif not isinstance(basis.get("references", []), list) or not isinstance(basis.get("evidence", []), list):
            _error(errors, "invalid_basis_evidence", "basis.references and basis.evidence must be lists", f"{path}.basis")
        elif not basis.get("references") and not basis.get("evidence"):
            _error(errors, "empty_candidate_basis", "A candidate needs references or reproducible evidence", f"{path}.basis")
        if isinstance(basis, dict) and basis.get("kind") in {"signal", "discovery-evidence"} and isinstance(basis.get("signal"), dict):
            signal_result = validate_signal(basis["signal"])
            for error in signal_result["errors"]:
                _error(errors, error["code"], error["message"], f"{path}.basis.{error['path'].removeprefix('signal.')}")
            if basis["signal"].get("status") in {"rejected", "expired"}:
                _error(errors, "signal_unavailable", "A rejected or expired Contribution Signal cannot be selected", f"{path}.basis.signal.status")
            if basis.get("kind") == "discovery-evidence" and basis["signal"].get("kind") != "reproducible-evidence":
                _error(errors, "discovery_signal_kind_mismatch", "discovery-evidence basis must use a reproducible-evidence signal", f"{path}.basis.signal.kind")
        duplicate_search = candidate.get("duplicate_search")
        if not isinstance(duplicate_search, dict) or duplicate_search.get("checked") is not True:
            _error(errors, "duplicate_search_missing", "Duplicate-work evidence must be explicitly checked", f"{path}.duplicate_search")
        elif not isinstance(duplicate_search.get("matches"), list):
            _error(errors, "invalid_duplicate_matches", "duplicate_search.matches must be a list", f"{path}.duplicate_search.matches")
        elif duplicate_search.get("matches"):
            if candidate.get("recommendation") != "do_not_contribute":
                _error(errors, "duplicate_work_recommendation_mismatch", "A candidate with duplicate matches cannot recommend direct contribution", f"{path}.recommendation")
        if not isinstance(candidate.get("risk"), list):
            _error(errors, "invalid_risk", "risk must be a list", f"{path}.risk")
        elif not all(isinstance(item, str) for item in candidate["risk"]):
            _error(errors, "invalid_risk_item", "risk items must be strings", f"{path}.risk")
        scope = candidate.get("scope")
        if isinstance(scope, dict) and any(not isinstance(scope.get(key, []), list) for key in ("files", "modules")):
            _error(errors, "invalid_scope_list", "scope.files and scope.modules must be lists", f"{path}.scope")
    selection = menu.get("selection")
    if not isinstance(selection, dict):
        _error(errors, "invalid_selection", "selection must be an object", "selection")
    elif selection.get("selected_id") and selection["selected_id"] not in seen:
        _error(errors, "unknown_selected_candidate", "selection.selected_id is not present in candidates", "selection.selected_id")
    elif not isinstance(selection.get("confirmed"), bool):
        _error(errors, "invalid_selection_confirmation", "selection.confirmed must be boolean", "selection.confirmed")
    elif selection.get("confirmed") and selection.get("selected_id"):
        selected = _candidate_by_id(menu, selection["selected_id"])
        basis = selected.get("basis", {})
        if isinstance(basis, dict) and basis.get("kind") in {"signal", "discovery-evidence"} and not isinstance(basis.get("signal"), dict):
            _error(errors, "selected_signal_missing", "A confirmed signal-backed candidate needs a structured signal record", f"candidates[{selection['selected_id']}].basis.signal")
    return {"valid": not errors, "errors": errors, "candidate_count": len(candidates), "candidate_ids": sorted(seen)}


def select_candidate(menu: dict[str, Any], candidate_id: str, *, confirmed: bool) -> dict[str, Any]:
    """Record an explicit candidate selection without authorizing implementation."""

    validation = validate_candidate_menu(menu)
    if not validation["valid"]:
        raise ValueError(f"Cannot select from an invalid candidate menu: {validation['errors']}")
    _candidate_by_id(menu, candidate_id)
    selected = deepcopy(menu)
    selected["selection"] = {"selected_id": candidate_id, "confirmed": confirmed}
    selected_validation = validate_candidate_menu(selected)
    if not selected_validation["valid"]:
        raise ValueError(f"Cannot confirm this candidate selection: {selected_validation['errors']}")
    return selected


def bind_candidate(menu: dict[str, Any], packet: dict[str, Any], candidate_id: str | None = None) -> dict[str, Any]:
    """Bind a confirmed candidate's basis to a packet before contract work begins."""

    validation = validate_candidate_menu(menu)
    if not validation["valid"]:
        raise ValueError(f"Cannot bind from an invalid candidate menu: {validation['errors']}")
    selection = menu.get("selection", {})
    selected_id = candidate_id or selection.get("selected_id")
    if not isinstance(selected_id, str) or not selected_id.strip():
        raise ValueError("A candidate must be selected before binding")
    if selection.get("selected_id") != selected_id or selection.get("confirmed") is not True:
        raise ValueError("Candidate selection must be explicitly confirmed before binding")
    candidate = _candidate_by_id(menu, selected_id)
    if candidate.get("recommendation") == "do_not_contribute":
        raise ValueError("A do_not_contribute candidate cannot be bound to an implementation packet")
    if not isinstance(packet, dict) or packet.get("packet_version") != "0.1":
        raise ValueError("A contribution packet with packet_version 0.1 is required")
    basis = candidate.get("basis")
    if not isinstance(basis, dict):
        raise ValueError("Selected candidate has no valid contribution basis")
    if basis.get("kind") in {"signal", "discovery-evidence"} and not isinstance(basis.get("signal"), dict):
        raise ValueError("Selected signal-backed candidate has no structured signal record")
    if isinstance(basis.get("signal"), dict) and basis["signal"].get("status") in {"rejected", "expired"}:
        raise ValueError("A rejected or expired Contribution Signal cannot be bound")
    bound = deepcopy(packet)
    menu_repository = menu.get("repository")
    if not isinstance(menu_repository, str) or not menu_repository.strip():
        raise ValueError("Candidate menu has no repository identity")
    try:
        parse_repository_slug(menu_repository)
    except ValueError as exc:
        raise ValueError("Candidate menu repository must use the owner/name form") from exc
    packet_repository = bound.get("repository")
    if not isinstance(packet_repository, dict) or not packet_repository.get("owner") or not packet_repository.get("name"):
        previous = packet_repository if isinstance(packet_repository, dict) else {}
        bound["repository"] = repository_identity(
            menu_repository,
            repository_id=previous.get("repository_id"),
            default_branch=str(previous.get("default_branch", "main") or "main"),
            base_sha=str(previous.get("base_sha", "") or ""),
        )
    elif not repository_matches(packet_repository, menu_repository):
        raise ValueError("Candidate menu repository does not match packet.repository")
    entry = bound.get("entry", {})
    if not isinstance(entry, dict):
        raise ValueError("packet_entry_invalid")
    bound["entry"] = dict(entry)
    bound["entry"]["mode"] = "issue-backed" if basis.get("kind") == "issue" else "discovery"
    bound["entry"]["source"] = f"candidate-menu:{menu.get('repository', '')}:{selected_id}"
    bound["basis"] = deepcopy(basis)
    bound["candidate_selection"] = {
        "candidate_id": selected_id,
        "repository": menu_repository,
        "menu_snapshot": sha256_json(menu),
        "recommendation": candidate.get("recommendation"),
        "confirmed": True,
    }
    return bound


def render_candidate_menu(menu: dict[str, Any]) -> str:
    validation = validate_candidate_menu(menu)
    if not validation["valid"]:
        raise ValueError(f"Cannot render invalid candidate menu: {validation['errors']}")
    lines = [
        "# Candidate menu",
        "",
        f"- Repository: `{menu['repository']}`",
        f"- Project brief: `{menu.get('project_brief') or 'not linked'}`",
        "- Ranking rule: evidence and maintainer review cost; no single confidence score.",
        "",
        "| ID | Candidate | Basis | Duplicate evidence | Value | Scope | Review cost | Verifiability | Risk | Recommendation |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in menu["candidates"]:
        basis = candidate["basis"]
        duplicate = candidate["duplicate_search"]
        value = candidate["value"]
        scope = candidate["scope"]
        matches = duplicate.get("matches") or []
        duplicate_text = f"checked ({len(matches)} match(es))"
        lines.append(
            "| {id} | {title} | {basis} | {duplicate} | {value} | {scope} | {cost} | {verify} | {risk} | {recommendation} |".format(
                id=candidate["id"],
                title=candidate["title"].replace("|", "\\|"),
                basis=basis.get("kind", "unknown"),
                duplicate=duplicate_text,
                value=str(value.get("summary", "")).replace("|", "\\|"),
                scope=", ".join(
                    [f"file:{item}" for item in scope.get("files", [])]
                    + [f"module:{item}" for item in scope.get("modules", [])]
                ) or "not bounded",
                cost=candidate["review_cost"],
                verify=candidate["verifiability"],
                risk=", ".join(candidate["risk"]) or "none recorded",
                recommendation=candidate["recommendation"],
            )
        )
    selected = menu["selection"].get("selected_id") or "none"
    lines.extend(["", f"Selected candidate: `{selected}`", ""])
    return "\n".join(lines)
