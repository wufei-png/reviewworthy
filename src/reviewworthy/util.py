"""Small standard-library helpers shared by the CLI and validators."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def normalize_label(value: Any) -> str:
    """Normalize GitHub state reasons and labels for exact policy checks."""

    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def has_normalized_label(labels: Any, expected: str) -> bool:
    if not isinstance(labels, list):
        return False
    target = normalize_label(expected)
    for label in labels:
        value = label.get("name") if isinstance(label, dict) else label
        if normalize_label(value) == target:
            return True
    return False
