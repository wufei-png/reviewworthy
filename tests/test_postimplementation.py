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
from reviewworthy.git import GitError, verification_plan_digest
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
        from reviewworthy.evidence import build_evidence_summary, validate_evidence_summary
        summary = build_evidence_summary(partial, partial['diff'])
        self.assertEqual(summary['claims']['verification'], {'claimed_outcome': 'not_recorded', 'receipt_count': 0})
        self.assertTrue(validate_evidence_summary(summary)['valid'])
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

    def test_verification_execution_errors_and_interruptions_withdraw_old_receipt(self) -> None:
        for failure in (GitError('Could not execute verification command: timed out'),
                        GitError('Could not execute verification command: executable missing'),
                        KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                packet = valid_packet()
                path = Path(directory) / 'packet.json'
                path.write_text(json.dumps(packet))
                args = ('verify', 'run', '--packet', str(path), '--check-id', 'unit')
                with patch('reviewworthy.cli.capture_pr_diff', return_value=packet['diff']), patch(
                        'reviewworthy.cli.run_verification', side_effect=failure):
                    if isinstance(failure, KeyboardInterrupt):
                        with self.assertRaises(KeyboardInterrupt):
                            self.call(*args)
                    else:
                        self.assertEqual(self.call(*args)[0], 2)
                current = json.loads(path.read_text())
                self.assertEqual(current['verification']['receipts'], [])
                self.assertEqual(node(current, 'verification')['status'], 'not_run')
                self.assertEqual(current['ownership']['status'], 'not_run')
                self.assertFalse(current['ai_assistance']['disclosure']['human_confirmed'])
                self.assertFalse(current['narrative']['final_preview_confirmed'])
                status = workflow_status(current, path)
                self.assertFalse(status['ready'])
                self.assertIn('--check-id unit', status['next'][0]['command'])
                # A later successful check restores verification, but cannot
                # silently reapprove the human evidence revoked by the failure.
                with patch('reviewworthy.cli.capture_pr_diff', return_value=packet['diff']), patch(
                        'reviewworthy.cli.run_verification', return_value=packet['verification']['receipts'][0]):
                    self.assertEqual(self.call(*args)[0], 0)
                self.assertEqual(self.call('next', '--packet', str(path))[1]['current_stage'], 'ownership')

    def test_identical_successful_cli_rerun_preserves_confirmed_human_evidence(self) -> None:
        packet = valid_packet()
        receipt = deepcopy(packet['verification']['receipts'][0])
        receipt.update(started_at='later', finished_at='later', stdout_sha256='new-output')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'packet.json'
            path.write_text(json.dumps(packet))
            with patch('reviewworthy.cli.capture_pr_diff', return_value=packet['diff']), patch(
                    'reviewworthy.cli.run_verification', return_value=receipt):
                self.assertEqual(self.call('verify', 'run', '--packet', str(path), '--check-id', 'unit')[0], 0)
            current = json.loads(path.read_text())
            self.assertTrue(workflow_status(current, path)['ready'])
            self.assertEqual(current['ownership'], packet['ownership'])
            self.assertEqual(current['understanding'], packet['understanding'])
            self.assertEqual(current['narrative'], packet['narrative'])
            self.assertEqual(current['ai_assistance'], packet['ai_assistance'])

    def test_failed_rerun_keeps_other_required_check_receipts(self) -> None:
        packet = valid_packet()
        second = deepcopy(packet['verification']['plan']['checks'][0])
        second['id'] = 'second'
        packet['verification']['plan']['checks'].append(second)
        packet['verification']['plan_digest'] = verification_plan_digest(packet['verification']['plan'])
        first_receipt = packet['verification']['receipts'][0]
        first_receipt['plan_digest'] = packet['verification']['plan_digest']
        second_receipt = {**first_receipt, 'check_id': 'second'}
        packet['verification']['receipts'].append(second_receipt)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'packet.json'
            path.write_text(json.dumps(packet))
            with patch('reviewworthy.cli.capture_pr_diff', return_value=packet['diff']), patch(
                    'reviewworthy.cli.run_verification', side_effect=GitError('execution failed')):
                self.assertEqual(self.call('verify', 'run', '--packet', str(path), '--check-id', 'unit')[0], 2)
            current = json.loads(path.read_text())
            self.assertEqual(current['verification']['receipts'], [second_receipt])
            self.assertEqual(node(current, 'verification')['status'], 'not_run')


    def test_ownership_records_explicit_outcome_and_preserves_receipts(self) -> None:
        packet = valid_packet()
        with tempfile.TemporaryDirectory() as directory:
            path, source = Path(directory) / 'packet.json', Path(directory) / 'ownership.json'
            path.write_text(json.dumps(packet))
            ownership = deepcopy(packet['ownership'])
            ownership['problem'] = 'The contributor explained the concrete failure.'
            source.write_text(json.dumps(ownership))
            self.assertEqual(self.call('packet', 'ownership', 'record', '--packet', str(path), '--input', str(source))[0], 0)
            updated = json.loads(path.read_text())
            self.assertEqual(updated['ownership'], ownership)
            self.assertEqual(node(updated, 'ownership')['status'], 'passed')
            self.assertEqual(updated['verification']['receipts'], packet['verification']['receipts'])
            self.assertEqual(updated['understanding']['orientation']['status'], 'not_run')
            self.assertFalse(updated['narrative']['final_preview_confirmed'])
            for change in ({'problem': ''}, {'status': True}, {'receipts': []}):
                malformed = {**ownership, **change}
                source.write_text(json.dumps(malformed))
                before = path.read_bytes()
                self.assertEqual(self.call('packet', 'ownership', 'record', '--packet', str(path), '--input', str(source))[0], 2)
                self.assertEqual(path.read_bytes(), before)
            packet['verification']['receipts'] = []
            path.write_text(json.dumps(packet))
            source.write_text(json.dumps(ownership))
            before = path.read_bytes()
            self.assertEqual(self.call('packet', 'ownership', 'record', '--packet', str(path), '--input', str(source))[0], 2)
            self.assertEqual(path.read_bytes(), before)

    def test_ai_record_preserves_stage_claims_and_resets_changed_disclosure_confirmation(self) -> None:
        packet = valid_packet()
        with tempfile.TemporaryDirectory() as directory:
            path, source = Path(directory) / 'packet.json', Path(directory) / 'ai.json'
            path.write_text(json.dumps(packet))
            assistance = deepcopy(packet['ai_assistance'])
            assistance['stages'][0]['human_verified'] = False
            assistance['disclosure']['text'] = 'AI assistance was used for implementation.'
            source.write_text(json.dumps(assistance))
            args = ('packet', 'ai', 'record', '--packet', str(path), '--input', str(source))
            self.assertEqual(self.call(*args)[0], 0)
            updated = json.loads(path.read_text())
            self.assertFalse(updated['ai_assistance']['stages'][0]['human_verified'])
            self.assertFalse(updated['ai_assistance']['disclosure']['human_confirmed'])
            self.assertFalse(updated['narrative']['final_preview_confirmed'])
            self.assertEqual(updated['verification'], packet['verification'])
            self.assertEqual(updated['understanding'], packet['understanding'])
            # Same current content plus an explicit claim can confirm disclosure.
            self.assertEqual(self.call(*args)[0], 0)
            self.assertTrue(json.loads(path.read_text())['ai_assistance']['disclosure']['human_confirmed'])
            assistance['disclosure']['locations'] = ['other']
            source.write_text(json.dumps(assistance))
            self.assertEqual(self.call(*args)[0], 0)
            self.assertFalse(json.loads(path.read_text())['ai_assistance']['disclosure']['human_confirmed'])

    def test_ai_record_requires_policy_stages_locations_and_truthful_verification_claim(self) -> None:
        packet = valid_packet()
        packet['policy']['authoritative_claims'].update(disclosure_required=True,
            disclosure_locations=['pr_body'], disclosure_stages=['implementation', 'verification'])
        with tempfile.TemporaryDirectory() as directory:
            path, source = Path(directory) / 'packet.json', Path(directory) / 'ai.json'
            path.write_text(json.dumps(packet))
            for mutate in (
                lambda data: data['disclosure'].update(locations=['other']),
                lambda data: data.update(stages=[]),
                lambda data: data['stages'][0].update(human_verified=False),
                lambda data: data['disclosure'].update(human_confirmed='yes'),
                lambda data: data.update(receipts=[]),
            ):
                assistance = deepcopy(packet['ai_assistance'])
                mutate(assistance)
                source.write_text(json.dumps(assistance))
                before = path.read_bytes()
                self.assertEqual(self.call('packet', 'ai', 'record', '--packet', str(path), '--input', str(source))[0], 2)
                self.assertEqual(path.read_bytes(), before)


    def test_narrative_exact_preview_confirm_and_later_reapproval(self) -> None:
        packet = valid_packet()
        packet['policy']['authoritative_claims']['disclosure_required'] = True
        packet['narrative']['body'] += '\n' + packet['ai_assistance']['disclosure']['text']
        packet['snapshots']['semantic'] = semantic_snapshot(packet)
        for phase in packet['understanding'].values():
            phase['semantic_snapshot'] = packet['snapshots']['semantic']
        with tempfile.TemporaryDirectory() as directory:
            path, source = Path(directory) / 'packet.json', Path(directory) / 'body.md'
            path.write_text(json.dumps(packet))
            body = packet['narrative']['body'] + '\nA concrete explanation.\n'
            source.write_text(body)
            args = ('packet', 'narrative', 'record', '--packet', str(path), '--title', 'Exact title', '--body-file', str(source))
            self.assertEqual(self.call(*args)[0], 0)
            recorded = json.loads(path.read_text())
            self.assertFalse(recorded['narrative']['final_preview_confirmed'])
            self.assertEqual(recorded['verification'], packet['verification'])
            before = path.read_bytes()
            preview_path = Path(directory) / 'preview.md'
            code, preview = self.call('packet', 'narrative', 'preview', '--packet', str(path), '--output', str(preview_path))
            self.assertEqual(code, 0)
            self.assertEqual(preview['body'], body)
            self.assertEqual(preview['confirmation_blockers'], [])
            self.assertEqual(preview_path.read_text(), body)
            self.assertEqual(path.read_bytes(), before)
            code, confirmed = self.call('packet', 'narrative', 'confirm', '--packet', str(path), '--human-confirmed')
            self.assertEqual(code, 0)
            self.assertTrue(confirmed['status']['ready'])
            current = json.loads(path.read_text())
            self.assertTrue(current['ai_assistance']['disclosure']['human_confirmed'])
            from reviewworthy.github import build_operation
            operation = build_operation(current, 'example/project', 'pull_request', 'Exact title', body, 'main', 'HEAD', current['diff'])
            self.assertEqual(operation.body, preview['public_body'].rstrip() + '\n\n' + operation.marker)
            # Identical recording preserves the approval.
            self.assertEqual(self.call(*args)[0], 0)
            self.assertTrue(json.loads(path.read_text())['narrative']['final_preview_confirmed'])
            source.write_text(body + 'Edited risk.\n')
            self.assertEqual(self.call(*args)[0], 0)
            self.assertFalse(json.loads(path.read_text())['narrative']['final_preview_confirmed'])
            self.assertIn('narrative preview', self.call('next', '--packet', str(path))[1]['next'][0]['command'])

    def test_confirmation_rejects_missing_link_disclosure_expression_and_current_evidence(self) -> None:
        from reviewworthy.packet_mutation import confirm_narrative
        for mutate in (
            lambda data: data['narrative'].update(body='No Issue URL'),
            lambda data: data['policy']['authoritative_claims'].update(disclosure_required=True),
            lambda data: data['policy']['authoritative_claims'].update(human_pr_narrative_required=True),
            lambda data: data['verification'].update(receipts=[]),
            lambda data: data['review'].update(profile='heightened'),
        ):
            packet = valid_packet()
            mutate(packet)
            with self.assertRaises(ValueError):
                confirm_narrative(packet, human_confirmed=True)
        with self.assertRaises(ValueError):
            confirm_narrative(valid_packet(), human_confirmed=False)

    def test_cli_standard_journey_reaches_remote_plan_with_real_receipts(self) -> None:
        import subprocess
        import sys
        from reviewworthy.contract import skeleton_contract
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'Test Contributor')
            git('config', 'user.email', 'test@example.invalid')
            (root / 'README.md').write_text('AI assistance is allowed.\nAI assistance must be disclosed in the PR body.\n')
            (root / 'src').mkdir()
            (root / 'src/example.py').write_text('one\n')
            git('add', '.')
            git('commit', '-qm', 'base')
            code, created = self.call('packet', 'init', '--root', str(root), '--contribution-id', 'journey')
            self.assertEqual(code, 0)
            path = Path(created['created'])
            source = root / '.git/input.json'
            self.assertEqual(self.call('packet', 'policy', 'bind', '--root', str(root), '--packet', str(path))[0], 0)
            self.assertEqual(self.call('packet', 'basis', 'record', '--packet', str(path), '--issue', 'https://github.com/example/project/issues/1')[0], 0)
            remote = {**valid_packet()['basis']['verification'], 'verified': True, 'labels': []}
            with patch('reviewworthy.cli.GhClient') as provider:
                provider.return_value.verify_public_reference.return_value = remote
                self.assertEqual(self.call('issue', 'verify', '--packet', str(path), '--record')[0], 0)
            contract = skeleton_contract('journey')
            contract.update(problem='Bounded failure', design='Guard the input', scope={'files': ['src/example.py']})
            source.write_text(json.dumps(contract))
            self.assertEqual(self.call('packet', 'contract', 'bind', '--packet', str(path), '--contract', str(source))[0], 0)
            self.assertEqual(self.call('packet', 'contract', 'approve', '--packet', str(path), '--human-confirmed')[0], 0)
            plan = {'plan_version': '0.1', 'checks': [{'id': 'unit', 'argv': [sys.executable, '-c', 'raise SystemExit(0)'], 'cwd': '.', 'required': True}]}
            source.write_text(json.dumps(plan))
            self.assertEqual(self.call('packet', 'verification', 'plan', '--packet', str(path), '--input', str(source))[0], 0)
            git('checkout', '-qb', 'contribution')
            (root / 'src/example.py').write_text('one\ntwo\n')
            git('add', 'src/example.py')
            git('commit', '-qm', 'implementation')
            self.assertEqual(self.call('diff', 'bind', '--root', str(root), '--packet', str(path), '--base', 'main', '--head', 'HEAD')[0], 0)
            self.assertEqual(self.call('next', '--packet', str(path))[1]['current_stage'], 'verification')
            self.assertEqual(self.call('verify', 'run', '--root', str(root), '--packet', str(path), '--check-id', 'unit')[0], 0)
            self.assertEqual(self.call('next', '--packet', str(path))[1]['current_stage'], 'ownership')
            source.write_text(json.dumps(valid_packet()['ownership']))
            self.assertEqual(self.call('packet', 'ownership', 'record', '--packet', str(path), '--input', str(source))[0], 0)
            source.write_text(json.dumps(valid_packet()['ai_assistance']))
            self.assertEqual(self.call('packet', 'ai', 'record', '--packet', str(path), '--input', str(source))[0], 0)
            body_path = root / '.git/body.md'
            body_path.write_text('https://github.com/example/project/issues/1\n\nFix the bounded failure.\n' + valid_packet()['ai_assistance']['disclosure']['text'] + '\n')
            self.assertEqual(self.call('packet', 'narrative', 'record', '--packet', str(path), '--title', 'Fix bounded failure', '--body-file', str(body_path))[0], 0)
            self.assertEqual(self.call('packet', 'narrative', 'preview', '--packet', str(path))[1]['confirmation_blockers'], [])
            self.assertEqual(self.call('packet', 'narrative', 'confirm', '--packet', str(path), '--human-confirmed')[0], 0)
            self.assertTrue(self.call('next', '--packet', str(path))[1]['ready'])
            args = ('remote', 'plan', '--root', str(root), '--packet', str(path), '--repo', 'example/project', '--kind', 'pull_request', '--title', 'Fix bounded failure', '--body-file', str(body_path), '--base', 'main', '--head', 'HEAD')
            with patch('reviewworthy.cli.GhClient') as provider:
                code, operation = self.call(*args)
                self.assertEqual(code, 0)
                self.assertEqual(operation['readiness_blockers'], [])
                provider.assert_not_called()
            current = json.loads(path.read_text())
            self.assertTrue(all(record['status'] == 'passed' and record['evidence'] for record in current['results']))
            self.assertEqual(current['verification']['receipts'][0]['provenance'], 'contributor_local')
            body_path.write_text(body_path.read_text() + '\n')
            self.assertEqual(self.call(*args)[0], 2)

    def test_heightened_and_learning_require_current_orientation_then_assessment(self) -> None:
        from reviewworthy.understanding import RUBRIC_CATEGORIES
        for profile in ('heightened', 'learning'):
            packet = valid_packet()
            packet['review']['profile'] = profile
            packet['narrative']['human_expression_required'] = True
            packet['narrative']['human_expression'] = ''
            packet['snapshots']['semantic'] = semantic_snapshot(packet)
            for phase in packet['understanding'].values():
                phase['status'] = 'not_run'
                phase['semantic_snapshot'] = packet['snapshots']['semantic']
            with tempfile.TemporaryDirectory() as directory:
                path, body_path, expression = (Path(directory) / name for name in ('packet.json', 'body.md', 'human.md'))
                path.write_text(json.dumps(packet))
                body_path.write_text(packet['narrative']['body'])
                expression.write_text('I chose the narrow boundary to preserve callers; the old exception behavior is the risk.')
                self.assertEqual(self.call('packet', 'narrative', 'record', '--packet', str(path), '--title', packet['narrative']['title'], '--body-file', str(body_path), '--human-expression-file', str(expression))[0], 0)
                rubric = [argument for category in sorted(RUBRIC_CATEGORIES) for argument in ('--rubric', f'{category}=Concrete contributor evidence for {category}.')]
                assessment = ('understanding', 'record', str(path), '--phase', 'assessment', '--status', 'passed', '--question', 'Which invariant protects callers?', '--answer', 'The existing input boundary preserves the caller contract.', *rubric)
                before = path.read_bytes()
                self.assertEqual(self.call(*assessment)[0], 2)
                self.assertEqual(path.read_bytes(), before)
                orientation = ('understanding', 'record', str(path), '--phase', 'orientation', '--status', 'passed', '--summary', 'Explained the current contract and failure path.', '--topic', 'contract', '--topic', 'diff', '--topic', 'verification', '--topic', 'policy', *rubric)
                self.assertEqual(self.call(*orientation)[0], 0)
                self.assertEqual(self.call('packet', 'narrative', 'confirm', '--packet', str(path), '--human-confirmed')[0], 2)
                self.assertEqual(self.call(*assessment)[0], 0)
                self.assertEqual(self.call('packet', 'narrative', 'confirm', '--packet', str(path), '--human-confirmed')[0], 0)
                changed_orientation = list(orientation)
                changed_orientation[changed_orientation.index('--summary') + 1] = 'A revised explanation of the failure path.'
                self.assertEqual(self.call(*changed_orientation)[0], 0)
                current = json.loads(path.read_text())
                self.assertEqual(current['understanding']['assessment']['status'], 'not_run')
                self.assertFalse(current['narrative']['final_preview_confirmed'])


    def test_partial_required_verification_still_previews_and_plans_valid_public_summary(self) -> None:
        from reviewworthy.evidence import extract_evidence_summary
        packet = valid_packet()
        second = deepcopy(packet['verification']['plan']['checks'][0])
        second['id'] = 'second'
        packet['verification']['plan']['checks'].append(second)
        packet['verification']['plan_digest'] = verification_plan_digest(packet['verification']['plan'])
        packet['verification']['receipts'][0]['plan_digest'] = packet['verification']['plan_digest']
        packet = maintain_packet(packet, packet)
        with tempfile.TemporaryDirectory() as directory:
            path, body = Path(directory) / 'packet.json', Path(directory) / 'body.md'
            path.write_text(json.dumps(packet))
            body.write_text(packet['narrative']['body'])
            code, preview = self.call('packet', 'narrative', 'preview', '--packet', str(path))
            self.assertEqual(code, 0)
            self.assertIn('required_verification_missing', {error['code'] for error in preview['confirmation_blockers']})
            self.assertEqual(extract_evidence_summary(preview['public_body'])['claims']['verification'],
                             {'claimed_outcome': 'not_recorded', 'receipt_count': 0})
            with patch('reviewworthy.cli.capture_pr_diff', return_value=packet['diff']):
                code, plan = self.call('remote', 'plan', '--packet', str(path), '--repo', 'example/project', '--kind', 'pull_request', '--title', packet['narrative']['title'], '--body-file', str(body), '--base', 'main', '--head', 'HEAD')
            self.assertEqual(code, 0)
            self.assertIn('required_verification_missing', {error['code'] for error in plan['readiness_blockers']})
            self.assertEqual(extract_evidence_summary(plan['body'])['claims']['verification'],
                             {'claimed_outcome': 'not_recorded', 'receipt_count': 0})


    def test_unstable_optional_receipt_routes_to_its_rerun_and_can_recover(self) -> None:
        packet = valid_packet()
        check = deepcopy(packet['verification']['plan']['checks'][0])
        check.update(id='optional', required=False)
        packet['verification']['plan']['checks'].append(check)
        packet['verification']['plan_digest'] = verification_plan_digest(packet['verification']['plan'])
        packet['verification']['receipts'][0]['plan_digest'] = packet['verification']['plan_digest']
        packet = maintain_packet(packet, packet)
        receipt = deepcopy(packet['verification']['receipts'][0])
        receipt.update(check_id='optional', integrity_status='invalid', worktree_clean_after=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'packet.json'
            path.write_text(json.dumps(packet))
            with patch('reviewworthy.cli.capture_pr_diff', return_value=packet['diff']), patch('reviewworthy.cli.run_verification', return_value=receipt):
                self.assertEqual(self.call('verify', 'run', '--packet', str(path), '--check-id', 'optional')[0], 1)
                status = self.call('next', '--packet', str(path))[1]
                self.assertEqual(status['current_stage'], 'verification')
                self.assertIn('--check-id optional', status['next'][0]['command'])
                self.assertIn('clean worktree', status['next'][0]['reason'])
                self.assertNotIn('Define at least one', status['next'][0]['reason'])
                self.assertEqual(node(json.loads(path.read_text()), 'verification')['status'], 'blocked')
                receipt.update(integrity_status='stable', worktree_clean_after=True)
                self.assertEqual(self.call('verify', 'run', '--packet', str(path), '--check-id', 'optional')[0], 0)
                self.assertEqual(node(json.loads(path.read_text()), 'verification')['status'], 'passed')
                self.assertEqual(self.call('next', '--packet', str(path))[1]['current_stage'], 'ownership')
