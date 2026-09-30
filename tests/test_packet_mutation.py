from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reviewworthy.cli import main
from reviewworthy.packet import readiness_blockers, semantic_snapshot, skeleton_packet
from reviewworthy.packet_mutation import maintain_packet, record_basis
from reviewworthy.signal import skeleton_signal

from helpers import valid_packet


def node(packet: dict, name: str) -> dict:
    return next(record for record in packet["results"] if record["node"] == name)


class PacketMutationTests(unittest.TestCase):
    def call(self, *args: str) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([*args, "--json"])
        return code, json.loads(output.getvalue())

    def test_policy_and_issue_record_progress_incomplete_packet_without_provider_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "packet.json"
            path.write_text(json.dumps(skeleton_packet("fresh", "issue-backed")))
            (root / "README.md").write_text("AI assistance is allowed.\n")
            with patch("reviewworthy.cli.GhClient") as provider:
                self.assertEqual(self.call("packet", "policy", "bind", "--root", str(root), "--packet", str(path))[0], 0)
                self.assertEqual(self.call("packet", "basis", "record", "--packet", str(path), "--issue", "https://github.com/example/project/issues/1")[0], 0)
                provider.assert_not_called()
            packet = json.loads(path.read_text())
            self.assertEqual(packet["repository"]["owner"], "example")
            self.assertNotIn("candidate_selection", packet)
            self.assertEqual(node(packet, "policy_check")["status"], "passed")
            self.assertEqual(node(packet, "contribution_basis")["status"], "blocked")
            self.assertIn("issue_verification_required", {error["code"] for error in readiness_blockers(packet)})

    def test_changed_basis_resets_approval_and_downstream_evidence_preserves_candidate_gates(self) -> None:
        packet = valid_packet()
        packet["candidate_selection"] = {"recommendation": "issue_only", "duplicate_disposition": "potential_duplicate"}
        updated = maintain_packet(packet, record_basis(packet, issue="https://github.com/example/project/issues/2"))
        self.assertEqual(updated["contract"]["approval"]["status"], "not_run")
        self.assertNotIn("verification", updated["basis"])
        self.assertEqual(updated["verification"]["receipts"], [])
        self.assertEqual(updated["understanding"]["orientation"]["status"], "not_run")
        self.assertEqual(updated["understanding"]["orientation"]["semantic_snapshot"], packet["understanding"]["orientation"]["semantic_snapshot"])
        self.assertFalse(updated["narrative"]["final_preview_confirmed"])
        self.assertEqual(node(updated, "implementation")["status"], "not_run")
        self.assertEqual(updated["candidate_selection"], packet["candidate_selection"])
        self.assertEqual(updated["snapshots"]["semantic"], semantic_snapshot(updated))

    def test_identical_issue_and_audit_refresh_preserve_current_evidence(self) -> None:
        packet = valid_packet()
        updated = maintain_packet(packet, record_basis(packet, issue=packet["basis"]["references"][0]))
        self.assertEqual(updated["contract"]["approval"], packet["contract"]["approval"])
        self.assertEqual(updated["verification"]["receipts"], packet["verification"]["receipts"])
        changed = deepcopy(packet)
        changed["basis"]["verification"]["verified_at"] = "later"
        updated = maintain_packet(packet, changed)
        self.assertEqual(updated["contract"]["approval"], packet["contract"]["approval"])
        self.assertEqual(updated["understanding"], packet["understanding"])

    def test_foreign_basis_and_invalid_signal_leave_packet_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(valid_packet()))
            before = path.read_bytes()
            code, _ = self.call("packet", "basis", "record", "--packet", str(path), "--issue", "https://github.com/other/project/issues/1")
            self.assertEqual(code, 2)
            self.assertEqual(path.read_bytes(), before)
        signal = skeleton_signal("issue", "bug_report", "https://github.com/example/project/issues/2")
        signal["verification"] = {"status": "verified", "provider": "github"}
        with self.assertRaises(ValueError):
            record_basis(valid_packet(), signal=signal)

    def test_unverified_external_signal_records_basis_but_cannot_pass_it(self) -> None:
        signal = skeleton_signal("discussion", "accepted_proposal", "https://github.com/example/project/discussions/3")
        packet = valid_packet()
        updated = maintain_packet(packet, record_basis(packet, signal=signal))
        self.assertEqual(node(updated, "contribution_basis")["status"], "blocked")
        self.assertIn("signal_verification_required", {error["code"] for error in readiness_blockers(updated)})

    def test_issue_verification_record_maintains_basis_result(self) -> None:
        packet = skeleton_packet("fresh", "issue-backed", "example/project")
        packet = maintain_packet(packet, record_basis(packet, issue="https://github.com/example/project/issues/1"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet))
            remote = {**valid_packet()["basis"]["verification"], "verified": True, "labels": []}
            with patch("reviewworthy.cli.GhClient") as provider:
                provider.return_value.verify_public_reference.return_value = remote
                self.assertEqual(self.call("issue", "verify", "--packet", str(path), "--record")[0], 0)
            updated = json.loads(path.read_text())
        self.assertEqual(node(updated, "contribution_basis")["status"], "passed")
        self.assertEqual(updated["repository"]["repository_id"], 101)

    def test_contract_bind_does_not_import_approval_and_approve_hashes_embedded_fields(self) -> None:
        packet = valid_packet()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, source = root / "packet.json", root / "contract.json"
            contract = deepcopy(packet["contract"])
            contract["design"] = "New bounded design"
            source.write_text(json.dumps(contract))
            source_before = source.read_bytes()
            path.write_text(json.dumps(packet))
            self.assertEqual(self.call("packet", "contract", "bind", "--packet", str(path), "--contract", str(source))[0], 0)
            bound = json.loads(path.read_text())
            self.assertEqual(bound["contract"]["approval"]["status"], "not_run")
            self.assertEqual(self.call("packet", "contract", "approve", "--packet", str(path), "--human-confirmed")[0], 0)
            approved = json.loads(path.read_text())
            from reviewworthy.contract import contract_snapshot
            self.assertEqual(approved["contract"]["approval"]["contract_sha256"], contract_snapshot(approved["contract"]))
            self.assertEqual(node(approved, "contribution_contract")["status"], "passed")
            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(self.call("packet", "contract", "approve", "--packet", str(path), "--human-confirmed")[0], 0)
            self.assertEqual(json.loads(path.read_text()), approved)

    def test_identical_contract_preserves_approval_and_material_fields_revoke_it(self) -> None:
        from reviewworthy.packet_mutation import bind_contract
        packet = valid_packet()
        identical = deepcopy(packet["contract"])
        identical.pop("approval")
        updated = maintain_packet(packet, bind_contract(packet, identical))
        self.assertEqual(updated["contract"]["approval"], packet["contract"]["approval"])
        self.assertEqual(updated["verification"]["receipts"], packet["verification"]["receipts"])
        for key, value in (("design", "New design"), ("scope", {"files": ["other.py"]})):
            with self.subTest(field=key):
                changed = deepcopy(identical)
                changed[key] = value
                updated = maintain_packet(packet, bind_contract(packet, changed))
                self.assertEqual(updated["contract"]["approval"]["status"], "not_run")
                self.assertEqual(updated["verification"]["receipts"], [])
                self.assertEqual(node(updated, "implementation")["status"], "not_run")

    def test_contract_approval_requires_policy_verified_basis_and_candidate_decision(self) -> None:
        from reviewworthy.packet_mutation import approve_contract
        cases = []
        no_basis = valid_packet()
        no_basis["basis"].pop("verification")
        cases.append(no_basis)
        no_policy = valid_packet()
        node(no_policy, "policy_check").update(status="not_run", evidence=[])
        cases.append(no_policy)
        candidate = valid_packet()
        candidate["candidate_selection"] = {"recommendation": "issue_only", "duplicate_disposition": "not_duplicate"}
        cases.append(candidate)
        for packet in cases:
            with self.assertRaises(ValueError):
                approve_contract(packet, human_confirmed=True)
        with self.assertRaises(ValueError):
            approve_contract(valid_packet(), human_confirmed=False)

    def test_contract_rejects_foreign_identity_arbitrary_records_and_invalid_paths(self) -> None:
        from reviewworthy.packet_mutation import bind_contract
        packet = valid_packet()
        for key, value in (("contribution_id", "other"), ("receipts", []), ("scope", {"files": ["../outside.py"]}), ("risks", [42])):
            contract = deepcopy(packet["contract"])
            contract[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                bind_contract(packet, contract)

    def test_review_escalates_preserves_hard_stops_and_never_downgrades_learning(self) -> None:
        from reviewworthy.packet_mutation import record_review
        from reviewworthy.risk import assess_manifest
        packet = valid_packet()
        assessed = assess_manifest({"public_api": True, "security_issue": True})
        updated = maintain_packet(packet, record_review(packet, assessed))
        self.assertEqual(updated["review"]["profile"], "heightened")
        self.assertEqual(updated["review"]["hard_stops"], assessed["hard_stops"])
        self.assertEqual(updated["contract"]["approval"], packet["contract"]["approval"])
        self.assertEqual(node(updated, "implementation")["status"], "passed")
        self.assertEqual(updated["verification"]["receipts"], [])
        low = {"profile": "standard", "signals": [], "hard_stops": []}
        preserved = maintain_packet(updated, record_review(updated, low))
        self.assertEqual(preserved["review"], updated["review"])
        learned = maintain_packet(updated, record_review(updated, {"profile": "learning"}))
        self.assertEqual(record_review(learned, low)["review"]["profile"], "learning")

    def test_verification_plan_preserves_exact_command_and_invalidates_receipts(self) -> None:
        from reviewworthy.git import verification_plan_digest
        from reviewworthy.packet_mutation import record_verification_plan
        packet = valid_packet()
        plan = {"plan_version": "0.1", "checks": [
            {"id": "special", "argv": ["python", "a b.py", "--literal=$HOME"], "cwd": "tests", "required": False},
            {"id": "required", "argv": ["python", "-m", "unittest"], "cwd": ".", "required": True},
        ]}
        updated = maintain_packet(packet, record_verification_plan(packet, plan))
        self.assertEqual(updated["verification"]["plan"], plan)
        self.assertEqual(updated["verification"]["plan_digest"], verification_plan_digest(plan))
        self.assertEqual(updated["verification"]["receipts"], [])
        self.assertEqual(updated["contract"]["approval"], packet["contract"]["approval"])
        self.assertEqual(node(updated, "verification")["status"], "not_run")
        self.assertEqual(node(updated, "implementation")["status"], "passed")
        unchanged = maintain_packet(packet, record_verification_plan(packet, packet["verification"]["plan"]))
        self.assertEqual(unchanged["verification"], packet["verification"])
        self.assertEqual(unchanged["understanding"], packet["understanding"])

    def test_review_and_plan_commands_reject_arbitrary_records_and_bad_plan_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            source = Path(directory) / "input.json"
            path.write_text(json.dumps(valid_packet()))
            before = path.read_bytes()
            cases = [
                ("review", "record", {"profile": "standard", "results": []}),
                ("verification", "plan", {"plan_version": "0.1", "checks": [], "receipts": []}),
                ("verification", "plan", {"plan_version": "0.1", "checks": [{"id": "unit", "argv": ["python"], "cwd": "../escape", "required": True}]}),
                ("verification", "plan", {"plan_version": "0.1", "checks": [{"id": "unit", "argv": [], "cwd": ".", "required": True}]}),
            ]
            for section, operation, payload in cases:
                source.write_text(json.dumps(payload))
                self.assertEqual(self.call("packet", section, operation, "--packet", str(path), "--input", str(source))[0], 2)
                self.assertEqual(path.read_bytes(), before)
            source.write_text(json.dumps({"profile": "heightened", "signals": [], "hard_stops": []}))
            self.assertEqual(self.call("packet", "review", "record", "--packet", str(path), "--input", str(source))[0], 0)
            self.assertEqual(json.loads(path.read_text())["review"]["profile"], "heightened")
            source.write_text(json.dumps({"plan_version": "0.1", "checks": [{"id": "unit", "argv": ["python"], "cwd": ".", "required": True}]}))
            self.assertEqual(self.call("packet", "verification", "plan", "--packet", str(path), "--input", str(source))[0], 0)

    def test_cli_only_preimplementation_journey_uses_next_without_manual_packet_edits(self) -> None:
        import shlex
        import subprocess
        from reviewworthy.contract import skeleton_contract
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "README.md").write_text("AI assistance is allowed.\n")
            code, created = self.call("packet", "init", "--root", str(root), "--contribution-id", "journey")
            self.assertEqual(code, 0)
            path = Path(created["created"])
            code, status = self.call("next", "--packet", str(path))
            self.assertEqual(status["current_stage"], "basis")
            self.assertIn("packet policy bind", status["next"][0]["command"])
            self.assertEqual(self.call("packet", "policy", "bind", "--root", str(root), "--packet", str(path))[0], 0)
            self.assertIn("packet basis record", self.call("next", "--packet", str(path))[1]["next"][0]["reason"])
            self.assertEqual(self.call("packet", "basis", "record", "--packet", str(path), "--issue", "https://github.com/example/project/issues/1")[0], 0)
            verify = self.call("next", "--packet", str(path))[1]["next"][0]["command"]
            remote = {**valid_packet()["basis"]["verification"], "verified": True, "labels": []}
            with patch("reviewworthy.cli.GhClient") as provider:
                provider.return_value.verify_public_reference.return_value = remote
                self.assertEqual(self.call(*shlex.split(verify)[1:-1])[0], 0)
            status = self.call("next", "--packet", str(path))[1]
            self.assertEqual(status["current_stage"], "contract")
            self.assertIn("packet contract bind", status["next"][0]["reason"])
            contract = skeleton_contract("journey")
            contract.update(problem="Bounded regression", design="Guard invalid input", scope={"files": ["src/example.py"]})
            source = root / "contract.json"
            source.write_text(json.dumps(contract))
            self.assertEqual(self.call("packet", "contract", "bind", "--packet", str(path), "--contract", str(source))[0], 0)
            self.assertIn("packet contract approve", self.call("next", "--packet", str(path))[1]["next"][0]["reason"])
            self.assertEqual(self.call("packet", "contract", "approve", "--packet", str(path), "--human-confirmed")[0], 0)
            status = self.call("next", "--packet", str(path))[1]
            self.assertEqual(status["current_stage"], "verification")
            self.assertIn("packet verification plan", status["next"][0]["reason"])
            source.write_text(json.dumps({"profile": "learning", "signals": [], "hard_stops": []}))
            self.assertEqual(self.call("packet", "review", "record", "--packet", str(path), "--input", str(source))[0], 0)
            source.write_text(json.dumps(valid_packet()["verification"]["plan"]))
            self.assertEqual(self.call("packet", "verification", "plan", "--packet", str(path), "--input", str(source))[0], 0)
            status = self.call("next", "--packet", str(path))[1]
            self.assertEqual(status["current_stage"], "implementation")
            self.assertIn("diff bind", status["next"][0]["command"])
            packet = json.loads(path.read_text())
            for name in ("policy_check", "contribution_basis", "contribution_contract"):
                self.assertEqual(node(packet, name)["status"], "passed")
            self.assertEqual(packet["review"]["profile"], "learning")

    def test_local_signal_can_establish_identity_through_basis_command(self) -> None:
        packet = skeleton_packet("local-journey", "discovery")
        packet["policy"] = {"authoritative_claims": {"discovery_evidence_allowed": True}, "result": "passed"}
        signal = skeleton_signal("local_evidence", "reproducible_evidence", "local:reproduction")
        signal["evidence"] = ["python reproduce.py"]
        with tempfile.TemporaryDirectory() as directory:
            path, source = Path(directory) / "packet.json", Path(directory) / "signal.json"
            path.write_text(json.dumps(packet))
            source.write_text(json.dumps(signal))
            self.assertEqual(self.call("packet", "basis", "record", "--packet", str(path), "--signal", str(source), "--repository", "example/project")[0], 0)
            updated = json.loads(path.read_text())
            self.assertEqual(node(updated, "contribution_basis")["status"], "passed")
            self.assertEqual(updated["repository"]["owner"], "example")
            before = path.read_bytes()
            self.assertEqual(self.call("packet", "basis", "record", "--packet", str(path), "--signal", str(source), "--repository", "other/project")[0], 2)
            self.assertEqual(path.read_bytes(), before)

    def test_review_record_accepts_absent_optional_lists_and_rejects_malformed_present_lists(self) -> None:
        from reviewworthy.packet import validate_packet
        from reviewworthy.packet_mutation import record_review
        packet = valid_packet()
        packet["review"] = {"profile": "standard"}
        snapshot = semantic_snapshot(packet)
        packet["snapshots"]["semantic"] = snapshot
        for phase in ("orientation", "assessment"):
            packet["understanding"][phase]["semantic_snapshot"] = snapshot
        self.assertTrue(validate_packet(packet)["valid"])
        identical = maintain_packet(packet, record_review(packet, {"profile": "standard"}))
        self.assertEqual(identical["verification"]["receipts"], packet["verification"]["receipts"])
        self.assertEqual(identical["understanding"], packet["understanding"])
        with tempfile.TemporaryDirectory() as directory:
            path, source = Path(directory) / "packet.json", Path(directory) / "review.json"
            source.write_text(json.dumps({"profile": "heightened", "signals": [], "hard_stops": []}))
            path.write_text(json.dumps(packet))
            self.assertEqual(self.call("packet", "review", "record", "--packet", str(path), "--input", str(source))[0], 0)
            updated = json.loads(path.read_text())
            self.assertEqual(updated["review"], {"profile": "heightened"})
            for field in ("signals", "hard_stops"):
                malformed = deepcopy(packet)
                malformed["review"][field] = None
                path.write_text(json.dumps(malformed))
                before = path.read_bytes()
                self.assertEqual(self.call("packet", "review", "record", "--packet", str(path), "--input", str(source))[0], 2)
                self.assertEqual(path.read_bytes(), before)

    def test_verified_pr_and_discussion_signals_populate_immutable_identity_and_reject_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path, source = Path(directory) / "packet.json", Path(directory) / "signal.json"
            for record_type, route in (("discussion", "discussions"), ("pull_request", "pull")):
                with self.subTest(record_type=record_type):
                    signal = skeleton_signal(record_type, "accepted_proposal", f"https://github.com/example/project/{route}/3")
                    signal["verification"] = {
                        "status": "verified", "provider": "github", "record_type": record_type,
                        "reference": signal["reference"], "url": signal["reference"], "number": 3,
                        "verified_at": "2026-09-30T00:00:00Z", "host": "github.com",
                        "repository": "example/project", "repository_id": 101, "visibility": "public",
                    }
                    source.write_text(json.dumps(signal))
                    path.write_text(json.dumps(skeleton_packet("signal-identity", "discovery")))
                    self.assertEqual(self.call("packet", "basis", "record", "--packet", str(path), "--signal", str(source))[0], 0)
                    packet = json.loads(path.read_text())
                    self.assertEqual(packet["repository"]["repository_id"], 101)
                    self.assertEqual(node(packet, "contribution_basis")["status"], "passed")
                    self.assertEqual(packet["basis"]["signal"]["verification"], signal["verification"])
                    before = path.read_bytes()
                    signal["verification"]["repository_id"] = 202
                    source.write_text(json.dumps(signal))
                    self.assertEqual(self.call("packet", "basis", "record", "--packet", str(path), "--signal", str(source))[0], 2)
                    self.assertEqual(path.read_bytes(), before)
