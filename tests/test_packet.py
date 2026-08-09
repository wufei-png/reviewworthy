from __future__ import annotations

import unittest

from reviewworthy.packet import issue_basis_blockers, semantic_snapshot, policy_violations, readiness_blockers, skeleton_packet, validate_packet

from helpers import valid_packet


class PacketValidationTests(unittest.TestCase):
    def test_good_first_policy_uses_only_verified_issue_labels(self) -> None:
        packet = valid_packet()
        packet["policy"]["authoritative_claims"]["good_first_issue_ai_allowed"] = False
        packet["basis"]["labels"] = ["good-first-issue"]

        self.assertNotIn("good_first_issue_ai_disallowed", {item["code"] for item in policy_violations(packet, enforce_disclosure=False)})

        packet["basis"]["verification"]["labels"] = ["Good First Issue"]
        violations = policy_violations(packet, enforce_disclosure=False)

        self.assertIn("good_first_issue_ai_disallowed", {item["code"] for item in violations})
        self.assertEqual(next(item["path"] for item in violations if item["code"] == "good_first_issue_ai_disallowed"), "basis.verification.labels")

        packet["basis"]["verification"].pop("record_type")
        self.assertIn("good_first_issue_label_verification_required", {item["code"] for item in policy_violations(packet, enforce_disclosure=False)})

        packet["basis"]["verification"]["record_type"] = "issue"
        packet["repository"]["repository_id"] = None
        packet["basis"]["verification"]["repository_id"] = None
        self.assertIn("good_first_issue_label_verification_required", {item["code"] for item in policy_violations(packet, enforce_disclosure=False)})
        packet["repository"]["repository_id"] = 101
        packet["basis"]["verification"]["repository_id"] = 101

        packet["basis"]["verification"].update({
            "host": "attacker.invalid",
            "number": 999,
            "url": "https://github.com/example/project/issues/999",
        })
        self.assertIn("good_first_issue_label_verification_required", {item["code"] for item in policy_violations(packet, enforce_disclosure=False)})
        packet["basis"]["verification"].update({
            "host": "github.com",
            "number": 1,
            "url": "https://github.com/example/project/issues/1",
        })

        packet["basis"]["verification"]["labels"] = None
        self.assertIn("good_first_issue_label_verification_required", {item["code"] for item in policy_violations(packet, enforce_disclosure=False)})
        packet["basis"]["verification"]["labels"] = ["Good First Issue"]
        packet["basis"]["verification"]["number"] = True
        self.assertIn("good_first_issue_label_verification_required", {item["code"] for item in policy_violations(packet, enforce_disclosure=False)})
        packet["basis"]["verification"]["number"] = 1
        packet["basis"]["verification"]["repository_id"] = True
        self.assertIn("good_first_issue_label_verification_required", {item["code"] for item in policy_violations(packet, enforce_disclosure=False)})
        packet["basis"]["verification"]["repository_id"] = 101

        packet["basis"] = {
            "kind": "signal",
            "signal": {
                "kind": "issue",
                "reference": "https://github.com/example/project/issues/1",
                "verification": {
                    "status": "verified",
                    "provider": "github",
                    "record_type": "issue",
                    "reference": "https://github.com/example/project/issues/1",
                    "repository": "example/project",
                    "repository_id": 101,
                    "host": "github.com",
                    "number": 1,
                    "url": "https://github.com/example/project/issues/1",
                    "visibility": "public",
                    "labels": ["good-first-issue"],
                },
            },
        }
        signal_violations = policy_violations(packet, enforce_disclosure=False)

        self.assertEqual(next(item["path"] for item in signal_violations if item["code"] == "good_first_issue_ai_disallowed"), "basis.signal.verification.labels")

        packet["basis"]["signal"] = {
            "kind": "accepted-proposal",
            "verification": {"status": "verified", "record_type": "pull_request", "labels": ["good-first-issue"]},
        }

        self.assertNotIn("good_first_issue_ai_disallowed", {item["code"] for item in policy_violations(packet, enforce_disclosure=False)})

    def test_policy_ambiguity_is_not_reported_as_policy_conflict(self) -> None:
        packet = valid_packet()
        packet["policy"]["ambiguities"] = [{"key": "issue_required"}]

        codes = {item["code"] for item in policy_violations(packet, enforce_disclosure=False)}

        self.assertIn("policy_ambiguity", codes)
        self.assertNotIn("policy_conflict", codes)

    def test_non_current_packet_is_rejected_as_invalid_without_compatibility(self) -> None:
        packet = valid_packet()
        packet["packet_version"] = "0.1"

        errors = validate_packet(packet)["errors"]

        self.assertIn("invalid_packet_version", {error["code"] for error in errors})

    def test_packet_03_requires_complete_merge_base_diff_identity(self) -> None:
        packet = valid_packet()
        packet["diff"].pop("merge_base_sha")

        errors = validate_packet(packet)["errors"]

        self.assertIn("missing_diff_field", {error["code"] for error in errors})

    def test_packet_03_rejects_unknown_fingerprint_algorithm(self) -> None:
        packet = valid_packet()
        packet["diff"]["fingerprint_algorithm"] = "legacy-patch-v1"

        self.assertIn("invalid_fingerprint_algorithm", {error["code"] for error in validate_packet(packet)["errors"]})

    def test_contribution_id_must_be_safe_for_private_git_state_path(self) -> None:
        packet = valid_packet()
        packet["contribution_id"] = "../../escaped"

        self.assertIn("invalid_contribution_id", {error["code"] for error in validate_packet(packet)["errors"]})

    def test_valid_packet_contains_every_result_and_current_assessment(self) -> None:
        result = validate_packet(valid_packet())
        self.assertTrue(result["valid"], result["errors"])

    def test_standard_profile_requires_ownership_but_not_orientation_or_assessment(self) -> None:
        packet = valid_packet()
        packet["understanding"]["orientation"]["status"] = "not_run"
        packet["understanding"]["assessment"]["status"] = "not_run"

        self.assertNotIn("orientation_not_passed", {item["code"] for item in readiness_blockers(packet)})
        packet["ownership"]["status"] = "not_run"
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        self.assertIn("ownership_not_passed", {item["code"] for item in readiness_blockers(packet)})

    def test_learning_profile_requires_full_orientation_and_assessment(self) -> None:
        packet = valid_packet()
        packet["review"]["profile"] = "learning"
        packet["understanding"]["orientation"]["status"] = "not_run"
        packet["understanding"]["assessment"]["status"] = "not_run"
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)

        codes = {item["code"] for item in readiness_blockers(packet)}
        self.assertIn("orientation_not_passed", codes)
        self.assertIn("assessment_not_passed", codes)

    def test_semantic_snapshot_ignores_audit_timestamps_and_output_hashes(self) -> None:
        packet = valid_packet()
        before = semantic_snapshot(packet)
        packet["diff"]["captured_at"] = "2099-01-01T00:00:00Z"
        packet["verification"]["receipts"][0]["started_at"] = "2099-01-01T00:00:00Z"
        packet["verification"]["receipts"][0]["stdout_sha256"] = "different-audit-hash"

        self.assertEqual(semantic_snapshot(packet), before)
        packet["basis"]["verification"]["verified_at"] = "2099-01-02T00:00:00Z"
        self.assertEqual(semantic_snapshot(packet), before)
        packet["verification"]["receipts"][0]["command_outcome"] = "failed"
        self.assertNotEqual(semantic_snapshot(packet), before)

    def test_old_verification_fields_are_rejected_not_migrated(self) -> None:
        packet = valid_packet()
        packet["verification"]["commands"] = ["python -m unittest"]
        packet["verification"]["receipts"][0]["status"] = "valid"

        codes = {item["code"] for item in validate_packet(packet)["errors"]}
        self.assertIn("unknown_verification_field", codes)
        self.assertIn("unknown_verification_receipt_field", codes)

    def test_ownership_shape_is_required_even_before_it_passes(self) -> None:
        packet = valid_packet()
        packet["ownership"] = {"status": "not_run", "legacy_note": "old shape"}

        codes = {item["code"] for item in validate_packet(packet)["errors"]}
        self.assertIn("unknown_ownership_field", codes)
        self.assertIn("invalid_ownership_field", codes)
        self.assertIn("invalid_ownership_risks", codes)

    def test_packet_and_readiness_evaluators_are_total_for_malformed_values(self) -> None:
        malformed = [None, True, 7, "packet", [], {}, {"packet_version": "0.3", "review": []}, {"results": [None], "understanding": "bad"}]
        for value in malformed:
            with self.subTest(value=value):
                validation = validate_packet(value)
                blockers = readiness_blockers(value)
                self.assertFalse(validation["valid"])
                self.assertIsInstance(validation["errors"], list)
                self.assertIsInstance(blockers, list)

    def test_absolute_verification_cwd_is_rejected(self) -> None:
        packet = valid_packet()
        packet["verification"]["receipts"][0]["cwd"] = "/workspace/reviewworthy"

        codes = {error["code"] for error in validate_packet(packet)["errors"]}

        self.assertIn("absolute_verification_cwd", codes)

    def test_windows_absolute_verification_cwd_is_rejected_on_posix(self) -> None:
        for cwd in (r"C:\Users\alice\reviewworthy", r"\\server\share\reviewworthy", r"C:verification", r"\verification"):
            packet = valid_packet()
            packet["verification"]["receipts"][0]["cwd"] = cwd

            codes = {error["code"] for error in validate_packet(packet)["errors"]}

            self.assertIn("absolute_verification_cwd", codes, cwd)

    def test_remote_readiness_rejects_receipt_without_clean_worktree_proof(self) -> None:
        packet = valid_packet()
        packet["verification"]["receipts"][0].pop("worktree_clean_before")
        packet["verification"]["receipts"][0].pop("worktree_clean_after")
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertIn("missing_executed_verification", codes)

    def test_issue_state_reason_normalization_and_duplicate_label_are_independent(self) -> None:
        for state_reason in ("not_planned", "not-planned", "not planned"):
            packet = valid_packet()
            packet["basis"]["verification"]["state_reason"] = state_reason
            self.assertIn("issue_not_actionable", {blocker["code"] for blocker in issue_basis_blockers(packet)})

        for state_reason in ("completed", "reopened"):
            packet = valid_packet()
            packet["basis"]["verification"]["state_reason"] = state_reason
            self.assertNotIn("issue_not_actionable", {blocker["code"] for blocker in issue_basis_blockers(packet)})

        packet = valid_packet()
        packet["basis"]["verification"]["state_reason"] = "duplicate"
        self.assertNotIn("issue_not_actionable", {blocker["code"] for blocker in issue_basis_blockers(packet)})

        packet = valid_packet()
        packet["basis"]["verification"]["labels"] = ["Duplicate"]
        self.assertIn("issue_duplicate", {blocker["code"] for blocker in issue_basis_blockers(packet)})

        packet["basis"]["verification"]["state_reason"] = "not_planned"
        codes = {blocker["code"] for blocker in issue_basis_blockers(packet)}
        self.assertIn("issue_not_actionable", codes)
        self.assertIn("issue_duplicate", codes)

    def test_unresolved_candidate_duplicate_disposition_blocks_readiness(self) -> None:
        packet = valid_packet()
        packet["candidate_selection"] = {
            "candidate_id": "candidate-potential",
            "repository": "example/project",
            "menu_snapshot": "menu-sha",
            "recommendation": "seek_maintainer_signal",
            "duplicate_disposition": "potential_duplicate",
            "confirmed": True,
        }
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        self.assertIn("duplicate_work_unresolved", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_material_change_invalidates_assessment(self) -> None:
        packet = valid_packet()
        packet["review"]["profile"] = "heightened"
        packet["diff"]["additions"] = 99
        result = validate_packet(packet)
        codes = {error["code"] for error in result["errors"]}
        self.assertIn("semantic_snapshot_mismatch", codes)
        self.assertIn("stale_assessment", codes)

    def test_missing_node_result_is_invalid(self) -> None:
        packet = valid_packet()
        packet["results"] = [result for result in packet["results"] if result["node"] != "narrative"]
        result = validate_packet(packet)
        self.assertIn("missing_result_record", {error["code"] for error in result["errors"]})

    def test_missing_ai_disclosure_record_is_invalid(self) -> None:
        packet = valid_packet()
        packet["ai_assistance"].pop("disclosure")

        result = validate_packet(packet)

        self.assertIn("missing_ai_disclosure_record", {error["code"] for error in result["errors"]})

    def test_ai_used_false_cannot_retain_assistance_stages(self) -> None:
        packet = valid_packet()
        packet["ai_assistance"]["used"] = False

        result = validate_packet(packet)

        self.assertIn("ai_usage_record_conflict", {error["code"] for error in result["errors"]})

    def test_skeleton_records_all_nodes_and_semantic_snapshot(self) -> None:
        packet = skeleton_packet("draft-001", "discovery")
        self.assertEqual(len(packet["results"]), 7)
        self.assertEqual(packet["entry"]["mode"], "discovery")
        self.assertTrue(packet["snapshots"]["semantic"])

    def test_discovery_evidence_policy_can_block_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {"kind": "discovery-evidence", "evidence": ["reproduced failure"]}
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = False
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        blockers = readiness_blockers(packet)

        self.assertIn("discovery_evidence_disallowed", {blocker["code"] for blocker in blockers})

    def test_discovery_requires_a_structured_signal_record(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {"kind": "discovery-evidence", "evidence": ["reproduced failure"]}
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        blockers = readiness_blockers(packet)
        codes = {blocker["code"] for blocker in blockers}

        self.assertIn("missing_signal_record", codes)

    def test_pending_signal_allows_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "discovery-evidence",
            "evidence": ["reproduced failure"],
            "signal": {
                "signal_version": "0.1",
                "kind": "reproducible-evidence",
                "reference": "repro://input-regression",
                "status": "pending",
                "evidence": ["exit 1"],
                "published": False,
            },
        }
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertNotIn("signal_not_confirmed", codes)
        self.assertNotIn("signal_unavailable", codes)

    def test_external_signal_requires_recorded_public_verification(self) -> None:
        packet = valid_packet()
        packet["basis"] = {
            "kind": "signal",
            "references": ["https://github.com/example/project/issues/2"],
            "evidence": [],
            "signal": {
                "signal_version": "0.1",
                "kind": "issue",
                "reference": "https://github.com/example/project/issues/2",
                "status": "pending",
                "evidence": [],
                "published": True,
            },
        }
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        blockers = readiness_blockers(packet)

        self.assertIn("signal_verification_required", {blocker["code"] for blocker in blockers})

        packet["basis"]["signal"]["verification"] = {
            "status": "verified",
            "provider": "github",
            "reference": packet["basis"]["signal"]["reference"],
            "verified_at": "2026-08-06T00:00:00Z",
        }
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        self.assertNotIn("signal_verification_required", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_rejected_signal_blocks_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "discovery-evidence",
            "evidence": ["reproduced failure"],
            "signal": {
                "signal_version": "0.1",
                "kind": "reproducible-evidence",
                "reference": "repro://input-regression",
                "status": "rejected",
                "evidence": ["exit 1"],
                "published": False,
            },
        }
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        self.assertIn("signal_unavailable", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_unknown_discovery_policy_blocks_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "discovery-evidence",
            "evidence": ["reproduced failure"],
            "signal": {
                "signal_version": "0.1",
                "kind": "reproducible-evidence",
                "reference": "repro://input-regression",
                "status": "confirmed",
                "evidence": ["exit 1"],
                "published": False,
                "confirmed_at": "2026-08-06T00:00:00Z",
            },
        }
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        self.assertIn("discovery_evidence_policy_unknown", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_confirmed_discovery_signal_clears_signal_specific_blockers(self) -> None:
        packet = valid_packet()
        packet["entry"]["mode"] = "discovery"
        packet["basis"] = {
            "kind": "discovery-evidence",
            "evidence": ["reproduced failure"],
            "signal": {
                "signal_version": "0.1",
                "kind": "reproducible-evidence",
                "reference": "repro://input-regression",
                "status": "confirmed",
                "evidence": ["exit 1"],
                "published": False,
                "confirmed_at": "2026-08-06T00:00:00Z",
            },
        }
        packet["policy"]["authoritative_claims"]["discovery_evidence_allowed"] = True
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertNotIn("signal_not_confirmed", codes)
        self.assertNotIn("missing_signal_record", codes)
        self.assertNotIn("discovery_evidence_policy_unknown", codes)

    def test_remote_readiness_checks_scope_and_diff_budget(self) -> None:
        packet = valid_packet()
        packet["diff"] = {"changed_files": ["src/example.py", "src/unapproved.py"], "additions": 99, "deletions": 0}
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertIn("out_of_scope_files", codes)
        self.assertIn("diff_budget_exceeded", codes)

    def test_missing_diff_budget_blocks_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["contract"].pop("max_diff_lines")
        packet["diff"].pop("additions")
        packet["diff"].pop("deletions")
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        codes = {blocker["code"] for blocker in readiness_blockers(packet)}

        self.assertIn("missing_diff_budget", codes)

    def test_contract_approval_is_required_for_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["contract"]["approval"] = {"status": "not_run", "human_confirmed": False}

        self.assertIn("contract_not_approved", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_orientation_must_pass_before_assessment(self) -> None:
        packet = valid_packet()
        packet["review"]["profile"] = "heightened"
        packet["understanding"]["orientation"]["status"] = "not_run"

        self.assertIn("orientation_not_passed", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_verification_plan_is_required_for_remote_readiness(self) -> None:
        packet = valid_packet()
        packet["verification"] = {"plan": {"plan_version": "0.1", "checks": []}, "plan_digest": "stale", "receipts": []}
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        self.assertIn("missing_verification_plan", {blocker["code"] for blocker in readiness_blockers(packet)})

    def test_risk_signal_cannot_use_standard_depth(self) -> None:
        packet = valid_packet()
        packet["review"]["signals"] = ["public_api"]

        self.assertIn("review_profile_too_low", {error["code"] for error in validate_packet(packet)["errors"]})

    def test_heightened_review_requires_human_expression(self) -> None:
        packet = valid_packet()
        packet["review"]["profile"] = "heightened"
        packet["narrative"]["human_expression"] = ""
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        self.assertIn("missing_human_expression", {error["code"] for error in validate_packet(packet)["errors"]})

    def test_packet_and_contract_ids_must_match(self) -> None:
        packet = valid_packet()
        packet["contract"]["contribution_id"] = "other-contribution"
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        self.assertIn("contribution_id_mismatch", {error["code"] for error in validate_packet(packet)["errors"]})

    def test_missing_policy_posture_uses_conservative_remote_fallback(self) -> None:
        packet = valid_packet()
        packet["policy"].pop("posture")
        packet["ai_assistance"]["disclosure"] = {"text": "", "locations": [], "human_confirmed": False}
        packet["snapshots"]["semantic"] = semantic_snapshot(packet)
        packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)

        blockers = readiness_blockers(packet)

        self.assertIn("missing_ai_disclosure", {blocker["code"] for blocker in blockers})
