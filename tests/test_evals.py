from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from reviewworthy.evals import run_evals


class EvalContractTests(unittest.TestCase):
    def test_repository_fixture_suite_passes_with_exact_assertions(self) -> None:
        result = run_evals(Path(__file__).parents[1] / "evals" / "fixtures")

        self.assertEqual(result["result"], "passed")
        self.assertEqual(result["total"], 10)
        self.assertEqual(result["failed"], 0)

    def test_packet_eval_requires_exact_blocker_set_and_result(self) -> None:
        fixture = {
            "id": "missing-exact-assertions",
            "kind": "packet",
            "assert": {"blocker": "issue_required"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")

            result = run_evals(path)

        self.assertEqual(result["result"], "failed")
        self.assertIn("exact blocker_codes and result", result["cases"][0]["failures"][0])
