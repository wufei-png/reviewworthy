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

    def _assert_invalid(self, schema_name: str, value: dict) -> None:
        schema = self.schemas[schema_name]
        resolver = RefResolver.from_schema(schema, store=self.store)
        errors = list(Draft202012Validator(schema, resolver=resolver).iter_errors(value))
        self.assertTrue(errors, f"Expected {schema_name} to reject {value!r}")

    def test_all_schemas_are_valid_draft_2020_12_documents(self) -> None:
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)

    def test_generated_artifacts_validate_against_portable_schemas(self) -> None:
        packet = valid_packet()
        signal = skeleton_signal("issue", "bug_report", "https://github.com/example/project/issues/1")
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

    def test_signal_schema_binds_verification_record_type_to_signal_record_type(self) -> None:
        signal = skeleton_signal("issue", "bug_report", "https://github.com/example/project/issues/1")
        signal["verification"] = {
            "status": "verified",
            "provider": "github",
            "reference": signal["reference"],
            "record_type": "discussion",
            "verified_at": "2026-08-09T00:00:00Z",
        }

        self._assert_invalid("contribution-signal.schema.json", signal)

    def test_packet_schema_requires_candidate_recommendation(self) -> None:
        packet = valid_packet()
        packet["candidate_selection"] = {
            "candidate_id": "candidate-incomplete",
            "repository": "example/project",
            "menu_snapshot": "menu-sha",
            "duplicate_disposition": "not_duplicate",
            "confirmed": True,
        }

        self._assert_invalid("contribution-packet.schema.json", packet)

    def test_packet_schema_rejects_legacy_narrative_disclosure(self) -> None:
        packet = valid_packet()
        packet["narrative"]["ai_disclosure"] = "Legacy disclosure"

        self._assert_invalid("contribution-packet.schema.json", packet)

    def test_packet_schema_requires_complete_issue_verification_identity(self) -> None:
        packet = valid_packet()
        packet["basis"]["verification"] = {
            "status": "verified",
            "provider": "github",
            "reference": "https://github.com/example/project/issues/1",
            "verified_at": "2026-08-10T00:00:00Z",
        }

        self._assert_invalid("contribution-packet.schema.json", packet)

    def test_evidence_summary_schema_rejects_open_or_untyped_claims(self) -> None:
        packet = valid_packet()
        summary = build_evidence_summary(packet, packet["diff"])
        summary["claims"]["verification"]["private_packet_path"] = "private/packet.json"
        summary["claims"]["ai_disclosure"]["claimed_present"] = "yes"

        self._assert_invalid("evidence-summary.schema.json", summary)
