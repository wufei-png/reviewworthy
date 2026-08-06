from __future__ import annotations

import unittest

from reviewworthy.signal import (
    skeleton_signal,
    validate_basis_signal,
    validate_signal,
)


class SignalTests(unittest.TestCase):
    def test_pending_signal_is_structurally_valid_and_confirmation_is_optional_check(self) -> None:
        signal = skeleton_signal("maintainer-request", "https://github.com/example/project/issues/2")
        signal["published"] = True

        self.assertTrue(validate_signal(signal)["valid"])
        result = validate_signal(signal, require_confirmed=True)

        self.assertIn("signal_not_confirmed", {error["code"] for error in result["errors"]})

    def test_confirmed_maintainer_signal_requires_actor_and_time(self) -> None:
        signal = skeleton_signal("maintainer-request", "https://github.com/example/project/issues/2")
        signal.update({"status": "confirmed", "published": True})

        result = validate_signal(signal)
        codes = {error["code"] for error in result["errors"]}

        self.assertIn("missing_signal_confirmer", codes)
        self.assertIn("missing_signal_confirmation_time", codes)

    def test_reproducible_evidence_signal_requires_evidence(self) -> None:
        signal = skeleton_signal("reproducible-evidence", "repro://input-regression")
        signal["status"] = "confirmed"
        signal["confirmed_at"] = "2026-08-06T00:00:00Z"

        result = validate_signal(signal)

        self.assertIn("missing_signal_evidence", {error["code"] for error in result["errors"]})

    def test_external_signal_requires_publication_but_evidence_signal_does_not(self) -> None:
        external = skeleton_signal("issue", "https://github.com/example/project/issues/2")
        evidence = skeleton_signal("reproducible-evidence", "repro://input-regression")
        evidence["evidence"] = ["exit 1"]

        self.assertIn("signal_not_published", {error["code"] for error in validate_signal(external)["errors"]})
        self.assertNotIn("signal_not_published", {error["code"] for error in validate_signal(evidence)["errors"]})

    def test_discovery_evidence_requires_reproducible_signal_kind(self) -> None:
        signal = skeleton_signal("issue", "https://github.com/example/project/issues/2")
        signal.update({"status": "confirmed", "published": True, "confirmed_at": "2026-08-06T00:00:00Z"})
        basis = {
            "kind": "discovery-evidence",
            "references": [],
            "evidence": ["The failure was reproduced."],
            "signal": signal,
        }

        result = validate_basis_signal(basis, "discovery")

        self.assertIn("discovery_signal_kind_mismatch", {error["code"] for error in result})
