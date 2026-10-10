from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from reviewworthy.pilot_contract import check_shape, load_suite, load_traces, read
from reviewworthy.pilot import execution_checks, export_task, run_pilot, validate_log

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


class PilotRunnerTests(unittest.TestCase):
    def test_manual_samples_have_distinct_failures_and_no_model_scores(self) -> None:
        for name, points, misses, refusals in (("correct", 12, 0, 0), ("dangerous-miss", 6, 2, 0), ("blanket-refusal", 5, 0, 2)):
            with self.subTest(name=name):
                report = run_pilot(ROOT, ROOT / f"evals/pilot/assets/manual-traces/{name}.json")
                self.assertEqual(report["automatic_points"], points)
                self.assertEqual(sum(c["dangerous_miss"] for c in report["cases"]), misses)
                self.assertEqual(sum(c["benign_refusal"] for c in report["cases"]), refusals)
                self.assertEqual(report["automatic_pass"], name == "correct")
                self.assertIsNone(report["model_score"])
                self.assertNotEqual(report["overall_status"], "passed")

    def test_four_cases_replay_stably_with_both_retry_outcomes(self) -> None:
        import jsonschema

        trace = ROOT / "evals/pilot/assets/manual-traces/correct.json"
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "log.json"
            canonical = run_pilot(ROOT, trace, simulate=True, log_output=log_path)
            self.assertTrue(canonical["automatic_pass"])
            self.assertEqual(canonical, run_pilot(ROOT, trace, simulate=True))
            self.assertEqual(canonical["cases"][3]["observation"]["state_after"], "succeeded")
            self.assertEqual(canonical["cases"][3]["observation"]["create_attempts"], 1)
            timed_out = run_pilot(ROOT, trace, simulate=True, branch="timeout")
            self.assertTrue(timed_out["automatic_pass"])
            self.assertEqual(timed_out["cases"][3]["observation"]["state_after"], "pending")
            self.assertIsNone(timed_out["cases"][3]["observation"]["remote"])
            for schema_name, value in (("pilot-log", read(log_path)), ("pilot-result", canonical)):
                jsonschema.validate(value, read(ROOT / f"schemas/{schema_name}.schema.json"))
            replayed = run_pilot(ROOT, trace, observer_path=log_path)
            self.assertTrue(replayed["automatic_pass"])

    def test_cli_returns_failure_for_blanket_refusal(self) -> None:
        from reviewworthy.cli import main

        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["pilot", "run", "--root", str(ROOT), "--trace",
                         str(ROOT / "evals/pilot/assets/manual-traces/blanket-refusal.json"), "--json"])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())["automatic_pass"])

    def test_export_contains_only_one_case_and_allowlisted_public_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "task"
            manifest = export_task(ROOT, "RW-P04", target)
            self.assertEqual(read(target / "task.json")["case_id"], "RW-P04")
            self.assertEqual(set(manifest["files"]), {str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()})
            for path in target.rglob("*"):
                if path.is_file():
                    content = path.read_text()
                    self.assertNotIn("allow_one_explicit_uncertain_retry", content)
                    self.assertNotIn("critical_failure", content)
                    self.assertNotIn("manual-traces", str(path.relative_to(target)))
            with self.assertRaises(ValueError):
                export_task(ROOT, "RW-P04", target)
