from __future__ import annotations

import unittest

from reviewworthy.signal import skeleton_signal, validate_basis_signal, validate_signal


class SignalTests(unittest.TestCase):
    def test_axes_are_independent_and_confirmation_is_optional(self) -> None:
        signal = skeleton_signal(
            "issue",
            "maintainer_request",
            "https://github.com/example/project/issues/2",
        )

        self.assertTrue(validate_signal(signal)["valid"])
        result = validate_signal(signal, require_confirmed=True)

        self.assertIn("signal_not_confirmed", {error["code"] for error in result["errors"]})

    def test_confirmed_maintainer_claim_requires_authority(self) -> None:
        signal = skeleton_signal(
            "issue",
            "maintainer_request",
            "https://github.com/example/project/issues/2",
        )
        signal["lifecycle"] = "confirmed"

        result = validate_signal(signal)
        codes = {error["code"] for error in result["errors"]}

        self.assertIn("insufficient_signal_authority", codes)
        self.assertIn("missing_signal_authority", codes)

    def test_local_reproducible_evidence_requires_evidence(self) -> None:
        signal = skeleton_signal("local_evidence", "reproducible_evidence", "local:input-regression")

        result = validate_signal(signal)

        self.assertIn("missing_signal_evidence", {error["code"] for error in result["errors"]})

    def test_external_reference_must_match_record_type(self) -> None:
        signal = skeleton_signal(
            "discussion",
            "accepted_proposal",
            "https://github.com/example/project/issues/2",
        )

        self.assertIn("signal_reference_record_mismatch", {error["code"] for error in validate_signal(signal)["errors"]})

    def test_signal_verification_is_bound_to_reference_and_record_type(self) -> None:
        signal = skeleton_signal("issue", "bug_report", "https://github.com/example/project/issues/2")
        signal["verification"] = {
            "status": "verified",
            "provider": "github",
            "record_type": "discussion",
            "reference": "https://github.com/example/project/issues/1",
            "verified_at": "2026-08-06T00:00:00Z",
        }

        result = validate_signal(signal)
        codes = {error["code"] for error in result["errors"]}

        self.assertIn("stale_signal_verification", codes)
        self.assertIn("signal_verification_record_mismatch", codes)

    def test_discovery_evidence_requires_local_reproducible_shape(self) -> None:
        signal = skeleton_signal("issue", "bug_report", "https://github.com/example/project/issues/2")
        basis = {
            "kind": "discovery-evidence",
            "references": [],
            "evidence": ["The failure was reproduced."],
            "signal": signal,
        }

        result = validate_basis_signal(basis, "discovery")

        self.assertIn("discovery_signal_shape_mismatch", {error["code"] for error in result})

    def test_pre_03_signal_axes_are_rejected_not_migrated(self) -> None:
        old_signal = {
            "signal_version": "0.1",
            "kind": "issue",
            "status": "confirmed",
            "reference": "https://github.com/example/project/issues/2",
            "evidence": [],
            "published": True,
        }

        result = validate_signal(old_signal)
        codes = {error["code"] for error in result["errors"]}

        self.assertEqual(codes, {"invalid_signal_version"})
