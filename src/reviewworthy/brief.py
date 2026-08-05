"""Deterministic project-brief facts for the Skill-owned orientation step."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .policy import inspect_policy
from .util import relative_path, sha256_json


BRIEF_VERSION = "0.1"
HUMAN_SECTIONS = (
    "problem",
    "components",
    "relevant_execution_path",
    "constraints",
    "testing_approach",
    "unwanted_change_patterns",
)

_TOOLING_FILES = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "justfile",
    "tox.ini",
    "pytest.ini",
    "composer.json",
    "Gemfile",
)
_TEST_DIRECTORIES = {"test", "tests", "spec", "integration", "e2e"}
_TEST_FILE_MARKERS = ("test_", "_test.", ".spec.", ".test.")
_IGNORED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build"}


def _is_ignored(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in _IGNORED_PARTS or part.endswith(".egg-info") for part in relative.parts):
        return True
    return path.suffix.lower() in {".pyc", ".pyo"} or relative.parts[:2] == (".reviewworthy", "local")


def _file_record(path: Path, root: Path, kind: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": relative_path(path, root),
        "kind": kind,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _tooling_and_test_paths(root: Path) -> tuple[list[Path], list[Path]]:
    tooling: list[Path] = []
    tests: list[Path] = []
    for name in _TOOLING_FILES:
        path = root / name
        if path.is_file():
            tooling.append(path)

    for path in root.rglob("*"):
        if not path.is_file() or _is_ignored(path, root):
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in _TEST_DIRECTORIES:
            tests.append(path)
        elif any(marker in path.name.lower() for marker in _TEST_FILE_MARKERS):
            tests.append(path)
    return sorted(set(tooling)), sorted(set(tests))


def _brief_document_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for name in ("CONTEXT.md", "SKILL.md"):
        path = root / name
        if path.is_file():
            paths.append(path)
    for directory in (root / "references", root / "docs"):
        if directory.is_dir():
            paths.extend(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".markdown"} and not _is_ignored(path, root))
    return sorted(set(paths))


def _entrypoint_hints(root: Path, tooling: list[Path], test_paths: list[Path]) -> list[str]:
    names = {path.name for path in tooling}
    hints: list[str] = []
    if "pyproject.toml" in names or "setup.py" in names or "setup.cfg" in names:
        hints.extend(["python -m unittest", "python -m pytest"] if test_paths else ["python -m compileall"])
    if "package.json" in names:
        hints.append("npm test")
    if "Cargo.toml" in names:
        hints.append("cargo test")
    if "go.mod" in names:
        hints.append("go test ./...")
    if "Makefile" in names:
        hints.append("make test (if provided by the repository)")
    return sorted(set(hints))


def build_project_brief(root: Path, focus: list[str] | None = None) -> dict[str, Any]:
    """Collect repository facts without inventing architecture or project intent."""

    root = root.resolve()
    policy = inspect_policy(root)
    tooling, test_paths = _tooling_and_test_paths(root)
    source_paths: dict[str, tuple[Path, str]] = {}
    for source in policy["sources"]:
        path = root / str(source["path"])
        if path.is_file():
            source_paths[str(path.resolve())] = (path, str(source["kind"]))
    for path in _brief_document_paths(root):
        source_paths[str(path.resolve())] = (path, "project_document")
    for path in tooling:
        source_paths[str(path.resolve())] = (path, "tooling")
    for path in test_paths:
        source_paths[str(path.resolve())] = (path, "test_entrypoint")

    sources = [
        _file_record(path, root, kind)
        for path, kind in sorted(source_paths.values(), key=lambda item: relative_path(item[0], root))
    ]
    tooling_records = [relative_path(path, root) for path in tooling]
    test_records = [relative_path(path, root) for path in test_paths]
    brief: dict[str, Any] = {
        "brief_version": BRIEF_VERSION,
        "generated_by": "reviewworthy",
        "status": "source-manifest-only",
        "repository": {"name": root.name},
        "focus": list(focus or []),
        "sources": sources,
        "tooling": {
            "files": tooling_records,
            "test_paths": test_records,
            "entrypoint_hints": _entrypoint_hints(root, tooling, test_paths),
        },
        "policy": {
            "result": policy["result"],
            "posture": policy["posture"],
            "unknown_claims": policy["unknown_claims"],
            "hard_stops": policy["hard_stops"],
        },
        "human_sections": {
            "problem": "",
            "components": [],
            "relevant_execution_path": [],
            "constraints": [],
            "testing_approach": [],
            "unwanted_change_patterns": [],
        },
    }
    brief["source_manifest_sha256"] = sha256_json(
        {"sources": brief["sources"], "tooling": brief["tooling"], "policy": brief["policy"]}
    )
    return brief


def validate_project_brief(brief: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    def error(code: str, message: str, path: str) -> None:
        errors.append({"code": code, "message": message, "path": path})

    if brief.get("brief_version") != BRIEF_VERSION:
        error("unsupported_version", "brief_version must be 0.1", "brief_version")
    if brief.get("generated_by") != "reviewworthy":
        error("invalid_generator", "generated_by must be reviewworthy", "generated_by")
    if brief.get("status") != "source-manifest-only":
        error("invalid_status", "The deterministic brief must remain source-manifest-only", "status")
    if not isinstance(brief.get("repository"), dict) or not str(brief["repository"].get("name", "")).strip():
        error("missing_repository", "repository.name is required", "repository.name")
    sources = brief.get("sources")
    if not isinstance(sources, list):
        error("invalid_sources", "sources must be a list", "sources")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                error("invalid_source", "Each source must be an object", f"sources[{index}]")
                continue
            for key in ("path", "kind", "sha256", "bytes"):
                if key not in source:
                    error("missing_source_field", f"Source field is required: {key}", f"sources[{index}].{key}")
            if str(source.get("path", "")).startswith("/"):
                error("absolute_source_path", "Source paths must be repository-relative", f"sources[{index}].path")
    human_sections = brief.get("human_sections")
    if not isinstance(human_sections, dict):
        error("missing_human_sections", "human_sections is required for Skill/contributor-owned prose", "human_sections")
    else:
        for key in HUMAN_SECTIONS:
            if key not in human_sections:
                error("missing_human_section", f"Human section is required: {key}", f"human_sections.{key}")
    expected_manifest = sha256_json(
        {"sources": brief.get("sources", []), "tooling": brief.get("tooling", {}), "policy": brief.get("policy", {})}
    )
    if brief.get("source_manifest_sha256") != expected_manifest:
        error("manifest_hash_mismatch", "source_manifest_sha256 does not match deterministic facts", "source_manifest_sha256")
    return {"valid": not errors, "errors": errors}


def render_project_brief(brief: dict[str, Any]) -> str:
    validation = validate_project_brief(brief)
    if not validation["valid"]:
        raise ValueError(f"Cannot render invalid project brief: {validation['errors']}")
    repository = brief["repository"]["name"]
    tooling = brief["tooling"]
    policy = brief["policy"]
    lines = [
        "# Project brief",
        "",
        "> This file contains deterministic repository facts. The sections marked Skill/contributor-owned must be completed from project understanding; they are not inferred by this renderer.",
        "",
        "## Repository facts",
        "",
        f"- Repository: `{repository}`",
        f"- Brief version: `{brief['brief_version']}`",
        f"- Source manifest: `{brief['source_manifest_sha256']}`",
        f"- Policy posture: `{policy['posture']}`",
        f"- Policy result: `{policy['result']}`",
        "",
        "## Source manifest",
        "",
        "| Path | Kind | SHA-256 | Bytes |",
        "| --- | --- | --- | ---: |",
    ]
    for source in brief["sources"]:
        lines.append(f"| `{source['path']}` | {source['kind']} | `{source['sha256']}` | {source['bytes']} |")
    lines.extend(["", "## Tooling and test entrypoints", ""])
    lines.append("- Tooling files: " + (", ".join(f"`{value}`" for value in tooling["files"]) or "none recorded"))
    lines.append("- Test paths: " + (", ".join(f"`{value}`" for value in tooling["test_paths"]) or "none recorded"))
    lines.append("- Command hints: " + (", ".join(f"`{value}`" for value in tooling["entrypoint_hints"]) or "none inferred"))
    lines.extend(["", "## Policy findings", ""])
    lines.append("- Unknown claims: " + (", ".join(f"`{value}`" for value in policy["unknown_claims"]) or "none"))
    lines.append("- Hard stops: " + (", ".join(f"`{value['code']}`" for value in policy["hard_stops"]) or "none"))
    lines.extend(["", "## Skill/contributor-owned understanding", ""])
    labels = {
        "problem": "Problem",
        "components": "主要组件",
        "relevant_execution_path": "Relevant execution path",
        "constraints": "Key constraints",
        "testing_approach": "Testing approach",
        "unwanted_change_patterns": "Unwanted change patterns",
    }
    for key in HUMAN_SECTIONS:
        value = brief["human_sections"].get(key)
        lines.extend([f"### {labels[key]}", ""])
        if isinstance(value, str) and value.strip():
            lines.extend([value.strip(), ""])
        elif isinstance(value, list) and value:
            lines.extend([f"- {item}" for item in value])
            lines.append("")
        else:
            lines.extend(["<!-- Fill from project orientation; do not treat this placeholder as evidence. -->", ""])
    return "\n".join(lines).rstrip() + "\n"
