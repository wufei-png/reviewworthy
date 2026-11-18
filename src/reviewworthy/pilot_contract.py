"""Small, strict offline pilot contracts; no runtime schema dependency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

CASE_IDS = tuple(f"RW-P0{number}" for number in range(1, 5))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_shape(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
    document: dict[str, Any] | None = None,
) -> None:
    """Validate the deliberately limited schema vocabulary used by this pilot.

    Schemas are maintained with this validator and cross-checked with jsonschema
    in tests. This is not a general JSON Schema implementation.
    """
    if document is None:
        document = schema
    if "$ref" in schema:
        reference = schema["$ref"]
        if not reference.startswith("#/"):
            raise ValueError("Pilot schemas support only local references")
        target = document
        for component in reference[2:].split("/"):
            target = target[component]
        check_shape(value, target, path, document)
        return
    if "oneOf" in schema:
        matches = 0
        for variant in schema["oneOf"]:
            try:
                check_shape(value, variant, path, document)
                matches += 1
            except ValueError:
                pass
        if matches != 1:
            raise ValueError(f"{path}: must match exactly one pilot variant")
        return
    if "const" in schema and (
        type(value) is not type(schema["const"]) or value != schema["const"]
    ):
        raise ValueError(f"{path}: invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported value")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "null": type(None),
    }
    if "type" in schema and type(value) is not types[schema["type"]]:
        raise ValueError(f"{path}: expected {schema['type']}")
    if isinstance(value, dict):
        if set(schema.get("required", [])) - value.keys():
            raise ValueError(f"{path}: missing required fields")
        properties = schema.get("properties", {})
        if (
            schema.get("additionalProperties") is False
            and value.keys() - properties.keys()
        ):
            raise ValueError(f"{path}: unknown fields")
        for key, item in value.items():
            if key in properties:
                check_shape(item, properties[key], f"{path}.{key}", document)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get(
            "maxItems", len(value)
        ):
            raise ValueError(f"{path}: invalid item count")
        if schema.get("uniqueItems") and len(
            {json.dumps(v, sort_keys=True) for v in value}
        ) != len(value):
            raise ValueError(f"{path}: duplicate items")
        for index, item in enumerate(value):
            check_shape(item, schema.get("items", {}), f"{path}[{index}]", document)
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        raise ValueError(f"{path}: empty string")
    if (
        isinstance(value, str)
        and "pattern" in schema
        and re.search(schema["pattern"], value) is None
    ):
        raise ValueError(f"{path}: invalid spelling")
    if type(value) is int and value < schema.get("minimum", value):
        raise ValueError(f"{path}: below minimum")


def load_suite(root: Path) -> dict[str, Any]:
    """Load only integrity-checked assets from a trusted evaluator checkout."""
    manifest = read(root / "evals/pilot/manifest.json")
    if manifest.get("version") != "1.0" or manifest.get("oracle_version") != "2.0":
        raise ValueError("Unsupported pilot/oracle version")
    assets = root / "evals/pilot/assets"
    for relative, expected in manifest["assets"].items():
        path = assets / relative
        if (
            path.resolve().is_relative_to(assets.resolve()) is False
            or digest(path) != expected
        ):
            raise ValueError(f"Pilot asset integrity mismatch: {relative}")
    cases, oracles = {}, {}
    schema = read(root / "schemas/pilot-case.schema.json")
    for case_id in CASE_IDS:
        case = read(assets / f"agent-input/{case_id}.json")
        check_shape(case, schema)
        if (
            case["case_id"] != case_id
            or case["baseline_commit_sha"] != manifest["baseline_commit"]
        ):
            raise ValueError("Pilot case identity mismatch")
        cases[case_id] = case
        oracle = read(assets / f"hidden-oracle/{case_id}.json")
        check_shape(oracle, read(root / "schemas/pilot-oracle.schema.json"))
        if (
            oracle["case_id"] != case_id
            or oracle["baseline_commit_sha"] != manifest["baseline_commit"]
        ):
            raise ValueError("Pilot oracle identity mismatch")
        oracles[case_id] = oracle
    return {"manifest": manifest, "cases": cases, "oracles": oracles, "assets": assets}


def load_traces(path: Path, root: Path) -> dict[str, Any]:
    value = read(path)
    if isinstance(value, dict) and "case_id" in value and "traces" not in value:
        value = {
            "schema_version": "1.0",
            "origin": "candidate_answer",
            "traces": [value],
        }
    check_shape(value, read(root / "schemas/pilot-trace.schema.json"))
    ids = [trace["case_id"] for trace in value["traces"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate trace case ID")
    if value["origin"] == "manually_constructed" and (
        value.get("not_model_output") is not True
        or value.get("not_real_execution") is not True
    ):
        raise ValueError(
            "Manual samples must declare their non-model, non-execution origin"
        )
    return value
