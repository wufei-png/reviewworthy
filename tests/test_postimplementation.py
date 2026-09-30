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
from reviewworthy.git import verification_plan_digest
from reviewworthy.packet import semantic_snapshot
from reviewworthy.packet_mutation import maintain_packet
from reviewworthy.workflow import workflow_status
from helpers import valid_packet
from test_packet_mutation import node


class EvidenceMutationTests(unittest.TestCase):
    def call(self, *args: str) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([*args, '--json'])
        return code, json.loads(output.getvalue())

    def test_partial_failed_and_unstable_receipts_derive_results_without_discarding_evidence(self) -> None:
        packet = valid_packet()
        check = deepcopy(packet['verification']['plan']['checks'][0])
        check['id'] = 'second'
        packet['verification']['plan']['checks'].append(check)
        packet['verification']['plan_digest'] = verification_plan_digest(packet['verification']['plan'])
        packet['verification']['receipts'][0]['plan_digest'] = packet['verification']['plan_digest']
        partial = maintain_packet(packet, packet)
        self.assertEqual(node(partial, 'verification')['status'], 'not_run')
        self.assertEqual(len(partial['verification']['receipts']), 1)
        self.assertIn('--check-id second', workflow_status(partial, Path('packet.json'))['next'][0]['command'])
        second = deepcopy(partial['verification']['receipts'][0])
        second.update(check_id='second', exit_code=1, command_outcome='failed')
        updated = deepcopy(partial)
        updated['verification']['receipts'].append(second)
        failed = maintain_packet(partial, updated)
        self.assertEqual(node(failed, 'verification')['status'], 'failed')
        self.assertEqual(len(failed['verification']['receipts']), 2)
        self.assertEqual(failed['ownership']['status'], 'not_run')
        self.assertFalse(failed['narrative']['final_preview_confirmed'])
        second.update(exit_code=0, command_outcome='passed')
        updated = deepcopy(failed)
        updated['verification']['receipts'][-1] = second
        passed = maintain_packet(failed, updated)
        self.assertEqual(node(passed, 'verification')['status'], 'passed')
        for field, value in [('integrity_status', 'invalid'), ('plan_digest', 'stale'), ('head_sha', 'other')]:
            updated = deepcopy(passed)
            updated['verification']['receipts'][-1][field] = value
            blocked = maintain_packet(passed, updated)
            self.assertEqual(node(blocked, 'verification')['status'], 'blocked')

    def test_audit_only_rerun_preserves_ownership_understanding_and_confirmation(self) -> None:
        packet = valid_packet()
        updated = deepcopy(packet)
        updated['verification']['receipts'][0].update(started_at='later', finished_at='later', stdout_sha256='new-output')
        updated = maintain_packet(packet, updated)
        self.assertEqual(updated['ownership'], packet['ownership'])
        self.assertEqual(updated['understanding'], packet['understanding'])
        self.assertTrue(updated['narrative']['final_preview_confirmed'])
        self.assertEqual(updated['snapshots']['semantic'], semantic_snapshot(packet))

    def test_verify_cli_records_failed_rerun_and_truthful_result(self) -> None:
        packet = valid_packet()
        receipt = deepcopy(packet['verification']['receipts'][0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'packet.json'
            path.write_text(json.dumps(packet))
            args = ('verify', 'run', '--root', directory, '--packet', str(path), '--check-id', 'unit')
            with patch('reviewworthy.cli.capture_pr_diff', return_value=packet['diff']), patch('reviewworthy.cli.run_verification', return_value=receipt):
                receipt.update(command_outcome='failed', exit_code=1)
                self.assertEqual(self.call(*args)[0], 1)
                failed = json.loads(path.read_text())
                self.assertEqual(node(failed, 'verification')['status'], 'failed')
                receipt.update(command_outcome='passed', exit_code=0)
                self.assertEqual(self.call(*args)[0], 0)
                passed = json.loads(path.read_text())
                self.assertEqual(node(passed, 'verification')['status'], 'passed')
                self.assertEqual(len(passed['verification']['receipts']), 1)
