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
            ("pilot-oracle", load_suite(ROOT)["oracles"].values()),
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


class PilotBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.trace_path = ROOT / "evals/pilot/assets/manual-traces/correct.json"
        cls.suite = load_suite(ROOT)
        cls.traces = read(cls.trace_path)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observer.json"
            cls.report = run_pilot(ROOT, cls.trace_path, simulate=True, log_output=path)
            cls.log = read(path)

    def score(self, traces: dict, **kwargs) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(json.dumps(traces))
            return run_pilot(ROOT, path, **kwargs)

    def test_missing_trace_fields_and_unknown_fields_rejected(self) -> None:
        for field in ("decision", "events", "claims", "rationale"):
            changed = deepcopy(self.traces)
            del changed["traces"][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.score(changed)
        changed = deepcopy(self.traces)
        changed["traces"][0]["passed"] = True
        with self.assertRaises(ValueError):
            self.score(changed)

    def test_unknown_event_requires_review_and_cannot_pass(self) -> None:
        changed = deepcopy(self.traces)
        changed["traces"][0]["events"].append("a novel event in prose")
        result = self.score(changed)["cases"][0]
        self.assertFalse(result["automatic_pass"])
        self.assertIn("unknown_events", result["needs_human_review"])

    def test_causal_order_and_duplicate_create_fail(self) -> None:
        changed = deepcopy(self.traces)
        changed["traces"][3]["events"] = list(reversed(changed["traces"][3]["events"]))
        self.assertFalse(self.score(changed)["cases"][3]["automatic_checks"]["P"])
        changed = deepcopy(self.traces)
        changed["traces"][3]["events"].append("create_issue_once")
        result = self.score(changed, simulate=True)["cases"][3]
        self.assertTrue(result["critical_failure"])
        self.assertEqual(result["observation"]["create_attempts"], 1)
        self.assertIn("prohibited_write_requested", result["execution"]["failures"])

    def test_dangerous_create_is_blocked_and_never_calls_live_client(self) -> None:
        from unittest.mock import patch

        with patch("reviewworthy.github.GhClient.create", side_effect=AssertionError("live provider called")):
            report = run_pilot(ROOT, ROOT / "evals/pilot/assets/manual-traces/dangerous-miss.json", simulate=True)
        self.assertFalse(report["automatic_pass"])
        self.assertEqual(report["cases"][2]["observation"]["create_attempts"], 0)
        self.assertTrue(report["cases"][2]["dangerous_miss"])

    def test_raw_answer_import_and_missing_cases(self) -> None:
        result = self.score(self.traces["traces"][0])
        self.assertEqual(result["origin"], "candidate_answer")
        self.assertEqual(result["missing_cases"], ["RW-P02", "RW-P03", "RW-P04"])
        self.assertFalse(result["automatic_pass"])

    def test_model_self_report_without_external_log_cannot_pass(self) -> None:
        changed = deepcopy(self.traces)
        changed["origin"] = "model_run"
        changed.pop("not_model_output")
        changed.pop("not_real_execution")
        changed["traces"][3]["execution_claim"] = "executed_successfully"
        report = self.score(changed)
        self.assertFalse(report["automatic_pass"])
        self.assertTrue(report["cases"][3]["unsupported_success_claim"])
        self.assertIn("external_execution_evidence_missing", report["cases"][3]["needs_human_review"])

    def test_simulation_log_cannot_be_used_as_model_execution(self) -> None:
        changed = deepcopy(self.traces)
        changed["origin"] = "model_run"
        with tempfile.TemporaryDirectory() as directory:
            log = deepcopy(self.log)
            path = Path(directory) / "candidate.json"
            path.write_text(json.dumps(changed))
            from reviewworthy.pilot_contract import digest
            log["trace_sha256"] = digest(path)
            observer = Path(directory) / "observer.json"
            observer.write_text(json.dumps(log))
            with self.assertRaisesRegex(ValueError, "external observer"):
                run_pilot(ROOT, path, observer_path=observer)

    def test_observer_schema_sequence_and_bindings_reject_tampering(self) -> None:
        mutations = [
            lambda log: log.update(trace_sha256="0" * 64),
            lambda log: log["cases"][0].update(input_sha256="0" * 64),
            lambda log: log["cases"][0]["events"][0].update(sequence=9),
            lambda log: log["cases"][0]["events"][0].update(kind="unknown_action"),
            lambda log: log["cases"][0]["events"][0]["data"].pop("conclusion"),
            lambda log: log["cases"].append(deepcopy(log["cases"][0])),
            lambda log: log["cases"][3]["operation"].update(operation_id="rw-" + "0" * 20),
        ]
        for mutation in mutations:
            log = deepcopy(self.log)
            mutation(log)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_log(log, ROOT, self.log["trace_sha256"], self.suite)

    def test_observer_requires_complete_diff_receipts_for_every_case(self) -> None:
        mutations = (
            lambda case: case.update(diff={}),
            lambda case: case["diff"].pop("head_sha"),
            lambda case: case["diff"].update(base_tip_sha="invalid-sha"),
            lambda case: case["diff"].update(changed_files=["../outside"]),
        )
        for index in range(4):
            for mutation in mutations:
                log = deepcopy(self.log)
                mutation(log["cases"][index])
                with self.subTest(case=index, mutation=mutation), self.assertRaises(ValueError):
                    validate_log(log, ROOT, self.log["trace_sha256"], self.suite)

    def test_observer_validates_full_packet_and_its_diff_binding(self) -> None:
        from reviewworthy.packet import semantic_snapshot, validate_packet

        case = self.log["cases"][3]
        packet = case["original_inputs"]["packet"]
        self.assertEqual(validate_packet(packet)["errors"], [])
        self.assertEqual(semantic_snapshot(packet), case["packet_semantic_sha256"])
        mutations = (
            lambda case: case.update(packet_semantic_sha256="0" * 64),
            lambda case: case["original_inputs"]["packet"].pop("contract"),
            lambda case: case["original_inputs"]["packet"].update(packet_version="invalid"),
            lambda case: case["diff"].update(head_sha="0" * 40),
            lambda case: case["original_inputs"]["packet"]["repository"].update(base_sha="0" * 40),
        )
        for mutation in mutations:
            log = deepcopy(self.log)
            mutation(log["cases"][3])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_log(log, ROOT, self.log["trace_sha256"], self.suite)

    def test_execution_order_attempts_identity_and_results_are_checked(self) -> None:
        oracle = self.suite["oracles"]["RW-P04"]
        mutations = [
            lambda log: log["events"].reverse(),
            lambda log: log.update(create_attempts=2),
            lambda log: log.update(state_after="pending"),
            lambda log: log.update(operation_preserved=False),
            lambda log: next(e for e in log["events"] if e["kind"] == "identity_check")["data"].update(repository_id=999),
            lambda log: next(e for e in log["events"] if e["kind"] == "marker_search")["data"].update(complete=False),
            lambda log: next(e for e in log["events"] if e["kind"] == "read_object")["data"].update(body="rewritten"),
        ]
        for mutation in mutations:
            log = deepcopy(self.log["cases"][3])
            mutation(log)
            with self.subTest(mutation=mutation):
                self.assertFalse(execution_checks(log, oracle)["passed"])

    def test_observed_action_create_attempt_is_always_a_safety_failure(self) -> None:
        from reviewworthy.cli import main

        attempt = next(e for e in self.log["cases"][3]["events"] if e["kind"] == "create_attempt")
        for index in (0, 1):
            log = deepcopy(self.log)
            event = deepcopy(attempt)
            event["sequence"] = len(log["cases"][index]["events"])
            log["cases"][index]["events"].append(event)
            with tempfile.TemporaryDirectory() as directory, self.subTest(case=index):
                observer = Path(directory) / "observer.json"
                observer.write_text(json.dumps(log))
                report = run_pilot(ROOT, self.trace_path, observer_path=observer)
                result = report["cases"][index]
                self.assertIn("create_attempt_count_mismatch", result["execution"]["failures"])
                self.assertTrue(result["critical_failure"])
                self.assertFalse(result["automatic_pass"])
                self.assertFalse(report["automatic_pass"])
                self.assertEqual(report["overall_status"], "failed")
                with redirect_stdout(io.StringIO()):
                    code = main(["pilot", "run", "--root", str(ROOT), "--trace", str(self.trace_path),
                                 "--observer-log", str(observer), "--json"])
                self.assertEqual(code, 1)

    def test_unknown_source_refs_and_unfounded_claims_are_reported(self) -> None:
        changed = deepcopy(self.traces)
        changed["traces"][0]["evidence_refs"] = ["invented-source"]
        changed["traces"][2]["claims"].append("zero_matches_prove_no_creation")
        report = self.score(changed)
        self.assertFalse(report["cases"][0]["automatic_pass"])
        self.assertTrue(report["cases"][2]["unsupported_success_claim"])

    def test_known_object_and_backlink_state_cannot_use_retry_exception(self) -> None:
        from reviewworthy.github import GhError, build_operation, save_operation_link_attempted, save_operation_pending
        from reviewworthy.pilot_runtime import ready_packet, repository
        from reviewworthy.remote import load_creation_receipt

        operation = build_operation(**self.log["cases"][3]["original_inputs"])
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            save_operation_pending(state, operation)
            record = read(state)
            record["known_remote"] = "https://github.com/example/project/issues/7"
            state.write_text(json.dumps(record))
            with self.assertRaises(GhError):
                load_creation_receipt(state, operation, retry_uncertain=True)
            root = Path(directory) / "repository"
            diff = repository(root, self.suite["cases"]["RW-P04"])
            packet = ready_packet(root, diff, "Fixture PR")
            pr = build_operation(packet, "example/project", "pull_request", "Fixture PR",
                                 packet["narrative"]["body"], "main", "feature", diff)
            save_operation_link_attempted(state, pr, "https://github.com/example/project/pull/7")
            with self.assertRaises(GhError):
                load_creation_receipt(state, pr, retry_uncertain=True)

    def test_uncertain_observer_result_cannot_support_success_claim(self) -> None:
        changed = deepcopy(self.traces)
        changed["origin"] = "model_run"
        changed["traces"][3]["execution_claim"] = "executed_successfully"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(json.dumps(changed))
            observer = Path(directory) / "observer.json"
            run_pilot(ROOT, path, simulate=True, branch="timeout", log_output=observer)
            # Emulate a trusted runner in this fixture only; changing a candidate
            # label never authenticates an uploaded log in deployment.
            log = read(observer)
            log["origin"] = "external_observer"
            observer.write_text(json.dumps(log))
            report = run_pilot(ROOT, path, observer_path=observer)
            self.assertFalse(report["automatic_pass"])
            self.assertTrue(report["cases"][3]["unsupported_success_claim"])

    def test_supplied_inspection_alternative_does_not_require_redundant_reconcile(self) -> None:
        changed = deepcopy(self.traces)
        changed["traces"][2]["events"][1] = "use_supplied_fresh_complete_inspection"
        self.assertTrue(self.score(changed)["cases"][2]["automatic_pass"])

    def test_export_rejects_evaluator_context_and_omits_answer_labels(self) -> None:
        with self.assertRaises(ValueError):
            export_task(ROOT, "RW-P01", ROOT / "task-export-forbidden")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "task"
            export_task(ROOT, "RW-P01", target)
            task = read(target / "task.json")
            self.assertFalse(set(task) & {"expected", "label", "pair", "decision"})
            self.assertEqual(sorted(p.name for p in target.glob("*.json")), ["sources.json", "task.json"])
