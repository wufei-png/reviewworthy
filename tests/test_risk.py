from __future__ import annotations

import unittest

from reviewworthy.risk import assess_manifest


class RiskAssessmentTests(unittest.TestCase):
    def test_risk_signal_raises_depth_but_is_not_a_hard_stop(self) -> None:
        result = assess_manifest(
            {
                "requested_review_depth": "standard",
                "public_api": True,
                "changed_files": ["src/public_api.py"],
                "verifiable": True,
            }
        )

        self.assertEqual(result["review_depth"], "heightened")
        self.assertEqual(result["hard_stops"], [])
        self.assertEqual(result["signals"][0]["code"], "public_api")

    def test_user_can_raise_but_not_lower_depth(self) -> None:
        result = assess_manifest({"requested_review_depth": "heightened"})
        self.assertEqual(result["review_depth"], "heightened")

    def test_security_issue_is_an_independent_hard_stop(self) -> None:
        result = assess_manifest({"requested_review_depth": "standard", "security_issue": True})
        self.assertEqual(result["review_depth"], "standard")
        self.assertEqual(result["hard_stops"][0]["code"], "security_issue")
