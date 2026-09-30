from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from reviewworthy.cli import main
from reviewworthy.contract import skeleton_contract
from reviewworthy.git import local_state_path
from reviewworthy.github import GhClient


ISSUE = 'https://github.com/example/project/issues/1'


class ReadOnlyTransport:
    """Inject provider facts at the gh subprocess boundary; reject every write."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fail = False

    def __call__(self, argv: list[str], **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        if self.fail:
            return subprocess.CompletedProcess(argv, 1, '', 'interrupted provider read')
        if argv == ['gh', 'api', 'repos/example/project', '--method', 'GET']:
            result = {'id': 101, 'visibility': 'public', 'full_name': 'example/project'}
        elif argv == ['gh', 'api', 'repos/example/project/issues/1', '--method', 'GET']:
            result = {'html_url': ISSUE, 'state': 'open', 'labels': [], 'locked': False}
        else:
            raise AssertionError(f'Unexpected provider call: {argv}')
        return subprocess.CompletedProcess(argv, 0, json.dumps(result), '')


class OnboardingTests(unittest.TestCase):
    def call(self, *args: str) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([*args, '--json'])
        return code, json.loads(output.getvalue())

    def git(self, root: Path, *args: str) -> str:
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def repository(self, root: Path) -> None:
        self.git(root, 'init', '-q', '-b', 'main')
        self.git(root, 'config', 'user.name', 'Test Contributor')
        self.git(root, 'config', 'user.email', 'test@example.invalid')
        self.git(root, 'remote', 'add', 'origin', 'https://github.com/example/project.git')
        (root / 'README.md').write_text('AI assistance is allowed.\nAI assistance must be disclosed in the PR body.\n')
        (root / 'example.py').write_text('value = 1\n')
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-qm', 'base')

    def start(self, root: Path) -> tuple[int, dict]:
        return self.call('start', '--root', str(root), '--contribution-id', 'journey',
                         '--issue', ISSUE, '--focus', 'example.py')

    def test_start_and_repeat_preserve_approved_packet_and_human_brief(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repository(root)
            transport = ReadOnlyTransport()
            with patch('reviewworthy.cli.GhClient', side_effect=lambda: GhClient(transport)):
                code, result = self.start(root)
                self.assertEqual(code, 0, result)
                self.assertEqual(result['status']['current_stage'], 'contract')
                path, brief_path = Path(result['packet']), Path(result['brief'])
                self.assertTrue(path.is_relative_to(root.resolve() / '.git'))
                self.assertEqual(self.git(root, 'status', '--porcelain'), '')
                brief = json.loads(brief_path.read_text())
                self.assertEqual(brief['status'], 'source-manifest-only')
                self.assertEqual(brief['focus_files'][0]['path'], 'example.py')
                brief['human_sections']['problem'] = 'Contributor-owned project understanding.'
                brief_path.write_text(json.dumps(brief))
                source = root / '.git/contract.json'
                contract = skeleton_contract('journey')
                contract.update(problem='Bounded failure', design='Guard input', scope={'files': ['example.py']})
                source.write_text(json.dumps(contract))
                self.assertEqual(self.call('packet', 'contract', 'bind', '--packet', str(path), '--contract', str(source))[0], 0)
                self.assertEqual(self.call('packet', 'contract', 'approve', '--packet', str(path), '--human-confirmed')[0], 0)
                before = path.read_bytes(), brief_path.read_bytes()
                code, repeated = self.start(root)
                self.assertEqual(code, 0)
                self.assertTrue(repeated['reused_packet'])
                self.assertEqual((path.read_bytes(), brief_path.read_bytes()), before)
                self.assertEqual(len(transport.calls), 2)

    def test_provider_failure_returns_paths_and_retry_verifies_same_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repository(root)
            transport = ReadOnlyTransport()
            transport.fail = True
            with patch('reviewworthy.cli.GhClient', side_effect=lambda: GhClient(transport)):
                code, result = self.start(root)
                self.assertEqual(code, 1)
                self.assertEqual(result['status']['current_stage'], 'basis')
                brief_before = Path(result['brief']).read_bytes()
                transport.fail = False
                code, recovered = self.start(root)
                self.assertEqual(code, 0, recovered)
                self.assertEqual(recovered['packet'], result['packet'])
                self.assertEqual(Path(recovered['brief']).read_bytes(), brief_before)
                self.assertEqual(recovered['status']['current_stage'], 'contract')

    def test_interrupted_artifact_initialization_reuses_brief(self) -> None:
        from reviewworthy.util import atomic_write_json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repository(root)
            def interrupt(path, value):
                if path.name == 'packet.json':
                    raise OSError('interrupted Packet persistence')
                atomic_write_json(path, value)
            with patch('reviewworthy.onboarding.atomic_write_json', side_effect=interrupt):
                self.assertEqual(self.start(root)[0], 2)
            brief_path = local_state_path(root, 'reviewworthy/v0.3/contributions/journey/project-brief.json')
            brief = json.loads(brief_path.read_text())
            brief['human_sections']['problem'] = 'Retain during retry'
            brief_path.write_text(json.dumps(brief))
            before = brief_path.read_bytes()
            with patch('reviewworthy.cli.GhClient', side_effect=lambda: GhClient(ReadOnlyTransport())):
                self.assertEqual(self.start(root)[0], 0)
            self.assertEqual(brief_path.read_bytes(), before)

    def test_start_rejects_different_basis_origin_and_invalid_focus_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repository(root)
            with patch('reviewworthy.cli.GhClient', side_effect=lambda: GhClient(ReadOnlyTransport())):
                self.assertEqual(self.start(root)[0], 0)
            path = local_state_path(root, 'reviewworthy/v0.3/contributions/journey/packet.json')
            before = path.read_bytes()
            for issue, focus in [('https://github.com/example/project/issues/2', 'example.py'),
                                 ('https://github.com/other/project/issues/1', 'example.py'),
                                 (ISSUE, '../outside')]:
                with self.subTest(issue=issue, focus=focus), patch('reviewworthy.cli.GhClient') as provider:
                    self.assertEqual(self.call('start', '--root', str(root), '--contribution-id', 'journey',
                                              '--issue', issue, '--focus', focus)[0], 2)
                    self.assertEqual(path.read_bytes(), before)
                    provider.assert_not_called()

    def test_policy_hard_stop_is_visible_and_not_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.repository(root)
            (root / 'README.md').write_text('AI assistance is prohibited.\n')
            self.git(root, 'commit', '-qam', 'policy')
            with patch('reviewworthy.cli.GhClient', side_effect=lambda: GhClient(ReadOnlyTransport())):
                code, result = self.start(root)
            self.assertEqual(code, 0)
            self.assertEqual(result['status']['current_stage'], 'blocked')
            self.assertFalse(result['status']['ready'])
            self.assertEqual(result['status']['next'][0]['kind'], 'decision')

    def test_resume_reports_renamed_or_deleted_focus_without_replacing_artifacts(self) -> None:
        for operation in ('rename', 'delete'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.repository(root)
                with patch('reviewworthy.cli.GhClient', side_effect=lambda: GhClient(ReadOnlyTransport())):
                    code, started = self.start(root)
                self.assertEqual(code, 0)
                path, brief_path = Path(started['packet']), Path(started['brief'])
                source = path.parent / 'contract.json'
                contract = skeleton_contract('journey')
                contract.update(problem='Bounded failure', design='Guard input', scope={'files': ['example.py']})
                source.write_text(json.dumps(contract))
                self.assertEqual(self.call('packet', 'contract', 'bind', '--packet', str(path), '--contract', str(source))[0], 0)
                self.assertEqual(self.call('packet', 'contract', 'approve', '--packet', str(path), '--human-confirmed')[0], 0)
                before = path.read_bytes(), brief_path.read_bytes()
                if operation == 'rename':
                    self.git(root, 'mv', 'example.py', 'renamed.py')
                else:
                    self.git(root, 'rm', 'example.py')
                self.git(root, 'commit', '-qm', operation + ' focus')
                with patch('reviewworthy.cli.GhClient') as provider:
                    code, resumed = self.start(root)
                    provider.assert_not_called()
                self.assertEqual(code, 0, resumed)
                self.assertEqual(resumed['packet'], started['packet'])
                self.assertEqual(resumed['brief'], started['brief'])
                self.assertEqual(resumed['status']['current_stage'], 'verification')
                self.assertIn('invalid_focus_file', {error['code'] for error in resumed['brief_validation']['errors']})
                self.assertEqual((path.read_bytes(), brief_path.read_bytes()), before)
