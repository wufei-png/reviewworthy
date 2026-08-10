"""Deterministic review-profile signals and independent hard-stop detection."""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any


DEFAULT_HEIGHTENED_PATH_GLOBS = (
    ".github/workflows/**",
    "migrations/**",
    "**/migrations/**",
    "auth/**",
    "**/auth/**",
    "security/**",
    "**/security/**",
    "credentials/**",
    "**/credentials/**",
    "permissions/**",
    "**/permissions/**",
)


def _add_signal(signals: list[dict[str, str]], code: str, reason: str) -> None:
    signals.append({"code": code, "reason": reason})


def _add_hard_stop(stops: list[dict[str, str]], code: str, reason: str) -> None:
    if not any(stop["code"] == code for stop in stops):
        stops.append({"code": code, "reason": reason})


def assess_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    signals: list[dict[str, str]] = []
    hard_stops: list[dict[str, str]] = []

    requested = manifest.get("requested_review_profile", "standard")
    if requested not in {"standard", "heightened", "learning"}:
        raise ValueError("requested_review_profile must be standard, heightened, or learning")

    if manifest.get("security_issue"):
        _add_hard_stop(hard_stops, "security_issue", "Security issues must use the private reporting path.")
    if manifest.get("policy_conflict"):
        _add_hard_stop(hard_stops, "policy_conflict", "Contradictory contribution-policy sources require clarification.")
    if manifest.get("irreversible_change"):
        _add_hard_stop(hard_stops, "irreversible_change", "The change is marked as irreversible and needs a separate decision.")
    if manifest.get("verifiable") is False:
        _add_hard_stop(hard_stops, "unverifiable", "The contribution cannot currently be verified by the stated evidence.")

    if manifest.get("public_api"):
        _add_signal(signals, "public_api", "Changes a public API or externally consumed contract.")
    if manifest.get("data_security_impact"):
        _add_signal(signals, "data_security_impact", "Touches data handling, permissions, or security-sensitive behavior.")
    if manifest.get("behavior_change"):
        _add_signal(signals, "behavior_change", "Changes observable behavior beyond a purely internal refactor.")
    if manifest.get("low_verifiability"):
        _add_signal(signals, "low_verifiability", "Evidence is available but difficult to reproduce or observe.")

    raw_changed_files = manifest.get("changed_files", [])
    if not isinstance(raw_changed_files, list) or not all(isinstance(value, str) and value.strip() for value in raw_changed_files):
        _add_hard_stop(hard_stops, "invalid_risk_manifest", "changed_files must be a list of non-empty repository paths.")
        changed_files: list[str] = []
    else:
        changed_files = [value.replace("\\", "/") for value in raw_changed_files]
    raw_globs = manifest.get("heightened_path_globs", list(DEFAULT_HEIGHTENED_PATH_GLOBS))
    if not isinstance(raw_globs, list) or not all(isinstance(value, str) and value.strip() for value in raw_globs):
        _add_hard_stop(hard_stops, "invalid_risk_manifest", "heightened_path_globs must be a list of non-empty globs.")
        heightened_globs = list(DEFAULT_HEIGHTENED_PATH_GLOBS)
    else:
        heightened_globs = list(raw_globs)
    matched_path_rules = [
        {"path": path, "rule": rule}
        for path in changed_files
        for rule in heightened_globs
        if fnmatchcase(path.casefold(), rule.casefold())
    ]
    if matched_path_rules:
        first = matched_path_rules[0]
        signals.append({
            "code": "sensitive_path",
            "reason": "Changed files match a configured heightened-review path rule.",
            "path": first["path"],
            "rule": first["rule"],
        })

    diff = manifest.get("diff", {})
    if isinstance(diff, dict):
        additions = diff.get("additions", 0)
        deletions = diff.get("deletions", 0)
        max_lines = manifest.get("max_diff_lines", 400)
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in (additions, deletions, max_lines)):
            _add_hard_stop(hard_stops, "invalid_risk_manifest", "Diff line counts and max_diff_lines must be non-negative integers.")
        elif additions + deletions > max_lines:
            _add_signal(signals, "large_diff", f"Diff has {additions + deletions} changed lines, over the {max_lines}-line review budget.")
    elif diff is not None:
        _add_hard_stop(hard_stops, "invalid_risk_manifest", "diff must be an object when present.")

    user_escalated = bool(manifest.get("user_escalated"))
    if requested == "learning":
        profile = "learning"
    elif requested == "heightened" or user_escalated or signals:
        profile = "heightened"
    else:
        profile = "standard"
    return {
        "review_profile": profile,
        "signals": signals,
        "hard_stops": hard_stops,
        "user_escalated": user_escalated,
        "requested_review_profile": requested,
        "changed_files": changed_files,
        "heightened_path_globs": heightened_globs,
        "matched_path_rules": matched_path_rules,
    }
