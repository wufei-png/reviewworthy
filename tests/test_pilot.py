from copy import deepcopy
from pathlib import Path
import unittest

from reviewworthy.pilot_contract import check_shape, load_suite, load_traces, read

ROOT = Path(__file__).resolve().parents[1]


class PilotContractTests(unittest.TestCase):
    def test_assets_and_all_manual_samples_load(self) -> None:
        self.assertEqual(len(load_suite(ROOT)["cases"]), 4)
        for name in ("correct", "dangerous-miss", "blanket-refusal"):
            self.assertEqual(len(load_traces(ROOT / f"evals/pilot/assets/manual-traces/{name}.json", ROOT)["traces"]), 4)

    def test_missing_nested_fields_and_wrong_types_fail(self) -> None:
        case = deepcopy(load_suite(ROOT)["cases"]["RW-P04"])
        schema = read(ROOT / "schemas/pilot-case.schema.json")
        del case["observations"]["manual_inspection"]
        with self.assertRaises(ValueError):
            check_shape(case, schema)
        case = deepcopy(load_suite(ROOT)["cases"]["RW-P04"])
        case["current_retry_authorization"]["verified_user"] = 1
        with self.assertRaises(ValueError):
            check_shape(case, schema)

    def test_schemas_agree_with_test_only_jsonschema(self) -> None:
        import jsonschema

        for schema_name, values in (
            ("pilot-case", load_suite(ROOT)["cases"].values()),
            ("pilot-trace", [read(ROOT / f"evals/pilot/assets/manual-traces/{n}.json")
                             for n in ("correct", "dangerous-miss", "blanket-refusal")]),
        ):
            schema = read(ROOT / f"schemas/{schema_name}.schema.json")
            jsonschema.Draft202012Validator.check_schema(schema)
            for value in values:
                jsonschema.validate(value, schema)
