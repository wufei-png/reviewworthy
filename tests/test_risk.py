from __future__ import annotations

import unittest

from reviewworthy.risk import assess_manifest


class RiskAssessmentTests(unittest.TestCase):
    def test_risk_signal_raises_depth_but_is_not_a_hard_stop(self) -> None:
        result = assess_manifest(
            {
                "requested_review_profile": "standard",
                "public_api": True,
                "changed_files": ["src/public_api.py"],
                "verifiable": True,
            }
        )

        self.assertEqual(result["review_profile"], "heightened")
        self.assertEqual(result["hard_stops"], [])
        self.assertEqual(result["signals"][0]["code"], "public_api")

    def test_user_can_raise_but_not_lower_depth(self) -> None:
        result = assess_manifest({"requested_review_profile": "heightened"})
        self.assertEqual(result["review_profile"], "heightened")

    def test_learning_profile_is_explicit_and_not_reclassified(self) -> None:
        result = assess_manifest({"requested_review_profile": "learning", "public_api": True})
        self.assertEqual(result["review_profile"], "learning")

    def test_security_issue_is_an_independent_hard_stop(self) -> None:
        result = assess_manifest({"requested_review_profile": "standard", "security_issue": True})
        self.assertEqual(result["review_profile"], "standard")
        self.assertEqual(result["hard_stops"][0]["code"], "security_issue")
