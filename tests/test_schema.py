from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator, RefResolver

from reviewworthy.brief import build_project_brief
from reviewworthy.candidate import skeleton_menu
from reviewworthy.evidence import build_evidence_summary
from reviewworthy.signal import skeleton_signal

from helpers import valid_packet


ROOT = Path(__file__).parents[1]
SCHEMA_ROOT = ROOT / "schemas"


def _schemas() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMA_ROOT.glob("*.json"))
    }


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = _schemas()
        cls.store = {schema["$id"]: schema for schema in cls.schemas.values()}

    def _assert_valid(self, schema_name: str, value: dict) -> None:
        schema = self.schemas[schema_name]
        resolver = RefResolver.from_schema(schema, store=self.store)
        errors = sorted(
            Draft202012Validator(schema, resolver=resolver).iter_errors(value),
            key=lambda error: list(error.absolute_path),
        )
        self.assertEqual(
            errors,
            [],
            "Schema errors for %s: %s" % (schema_name, [error.message for error in errors]),
        )

    def test_all_schemas_are_valid_draft_2020_12_documents(self) -> None:
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)

    def test_generated_artifacts_validate_against_portable_schemas(self) -> None:
        packet = valid_packet()
        signal = skeleton_signal("issue", "https://github.com/example/project/issues/1")
        signal["published"] = True
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Example project.\n", encoding="utf-8")
            brief = build_project_brief(root, ["README.md"])

        self._assert_valid("ai-assistance.schema.json", packet["ai_assistance"])
        self._assert_valid("candidate-menu.schema.json", skeleton_menu("example/project"))
        self._assert_valid("contribution-contract.schema.json", packet["contract"])
        self._assert_valid("contribution-packet.schema.json", packet)
        self._assert_valid("evidence-summary.schema.json", build_evidence_summary(packet, packet["diff"]))
        self._assert_valid("contribution-signal.schema.json", signal)
        self._assert_valid("project-brief.schema.json", brief)
        self._assert_valid("understanding.schema.json", packet["understanding"])
