from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from reviewworthy.action import check_evidence
from reviewworthy.cli import main
from reviewworthy.git import capture_pr_diff, local_state_path
from reviewworthy.github import build_operation
from reviewworthy.packet import semantic_snapshot

from helpers import valid_packet


class PrivatePacketPublicSummaryE2ETests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    def test_private_packet_drives_public_summary_and_action_without_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            root.mkdir()
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Reviewworthy Test")
            self._git(root, "branch", "-M", "main")
            (root / "example.py").write_text("one\n", encoding="utf-8")
            self._git(root, "add", "example.py")
            self._git(root, "commit", "-qm", "base")
            self._git(root, "checkout", "-qb", "feature")
            (root / "example.py").write_text("one\ntwo\n", encoding="utf-8")
            self._git(root, "commit", "-qam", "feature")
            diff = capture_pr_diff(root, "main", "feature")

            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "packet", "init", "--root", str(root), "--contribution-id", "contribution-001",
                    "--repository", "example/project", "--json",
                ]), 0)
            packet_path = local_state_path(
                root, "reviewworthy/v0.3/contributions/contribution-001/packet.json"
            )
            self.assertIn("/.git/reviewworthy/v0.3/", packet_path.as_posix())

            packet = valid_packet()
            packet["diff"] = dict(diff)
            packet["verification"]["receipts"][0].update({
                "subject_digest": diff["subject_digest"],
                "head_sha": diff["head_sha"],
                "head_sha_before": diff["head_sha"],
                "head_sha_after": diff["head_sha"],
            })
            packet["snapshots"]["semantic"] = semantic_snapshot(packet)
            packet["understanding"]["orientation"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet["understanding"]["assessment"]["semantic_snapshot"] = semantic_snapshot(packet)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")

            operation = build_operation(
                packet, "example/project", "pull_request", packet["narrative"]["title"],
                packet["narrative"]["body"], "main", "feature", diff,
            )
            self.assertIn("reviewworthy:evidence-summary:start", operation.body)
            self.assertNotIn('"contract"', operation.body)
            result = check_evidence(
                operation.body,
                root=root,
                event_name="pull_request",
                event_repository="example/project",
                event_repository_id=101,
                event_base_sha=diff["base_tip_sha"],
                event_head_sha=diff["head_sha"],
                mode="evidence-enforce",
            )

            self.assertEqual(result["conclusion"], "success", result["violations"])


class OnboardingJourneyTests(unittest.TestCase):
    """Real Git and subprocess receipts; provider reads use a strict fake transport."""

    from test_onboarding import OnboardingTests as _Support
    call = _Support.call
    git = _Support.git
    repository = _Support.repository

    def stage(self, path: Path, expected: str) -> dict:
        import shlex
        from reviewworthy.cli import _build_parser
        code, result = self.call('next', '--packet', str(path))
        self.assertEqual(code, 0, result)
        self.assertEqual(result['current_stage'], expected, result)
        self.assertEqual(len(result['next']), 1)
        action = result['next'][0]
        if action['kind'] == 'command':
            self.assertNotIn('...', action['command'])
            tokens = shlex.split(action['command'])
            self.assertEqual(tokens.pop(0), 'reviewworthy')
            _build_parser().parse_args(tokens)
        else:
            self.assertEqual(action['command'], '')
            self.assertTrue(action['reason'])
        return result

    def journey(self, root: Path, shape: str) -> tuple[Path, Path, tuple[str, ...]]:
        import sys
        from unittest.mock import patch
        from reviewworthy.contract import skeleton_contract
        from reviewworthy.github import GhClient
        from test_onboarding import ISSUE, ReadOnlyTransport
        self.repository(root)
        tooling, focus, test_path, hint = {
            'python': ('pyproject.toml', 'src/boundary.py', 'tests/test_boundary.py', 'python -m unittest'),
            'node': ('package.json', 'src/boundary.js', 'tests/boundary.test.js', 'npm test'),
            'go': ('go.mod', 'boundary.go', 'boundary_test.go', 'go test ./...'),
        }[shape]
        for name, content in [(tooling, {'python': '[project]\nname="fixture"\n', 'node': '{"scripts":{"test":"fixture"}}\n', 'go': 'module example/project\n'}[shape]),
                              (focus, 'value = 1\n'), (test_path, 'fixture test entrypoint\n')]:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-qm', 'tooling shape')
        transport = ReadOnlyTransport()
        start_args = ('start', '--root', str(root), '--contribution-id', 'journey', '--issue', ISSUE, '--focus', focus)
        with patch('reviewworthy.cli.GhClient', side_effect=lambda: GhClient(transport)):
            code, started = self.call(*start_args)
            self.assertEqual(code, 0, started)
            path = Path(started['packet'])
            brief = json.loads(Path(started['brief']).read_text())
            self.assertIn(tooling, brief['tooling']['files'])
            self.assertIn(test_path, brief['tooling']['test_paths'])
            self.assertIn(hint, brief['tooling']['entrypoint_hints'])
            before = path.read_bytes()
            self.assertEqual(self.call(*start_args)[0], 0)
            self.assertEqual(path.read_bytes(), before)
        self.stage(path, 'contract')
        source = path.parent / 'input.json'
        contract = skeleton_contract('journey')
        contract.update(problem='Bounded failure', design='Guard the boundary', scope={'files': [focus]})
        source.write_text(json.dumps(contract))
        self.assertEqual(self.call('packet', 'contract', 'bind', '--packet', str(path), '--contract', str(source))[0], 0)
        self.stage(path, 'contract')
        self.assertEqual(self.call('packet', 'contract', 'approve', '--packet', str(path), '--human-confirmed')[0], 0)
        self.stage(path, 'verification')  # The check plan is a real unresolved decision.
        plan = {'plan_version': '0.1', 'checks': [{'id': 'boundary', 'argv': [sys.executable, '-c',
            f'from pathlib import Path; assert Path({focus!r}).read_text() == "value = 2\\n"'], 'cwd': '.', 'required': True}]}
        source.write_text(json.dumps(plan))
        self.assertEqual(self.call('packet', 'verification', 'plan', '--packet', str(path), '--input', str(source))[0], 0)
        self.stage(path, 'implementation')
        self.git(root, 'checkout', '-qb', 'contribution')
        (root / focus).write_text('value = 2\n')
        self.git(root, 'add', focus)
        self.git(root, 'commit', '-qm', 'implementation')
        self.assertEqual(self.call('diff', 'bind', '--root', str(root), '--packet', str(path), '--base', 'main', '--head', 'HEAD')[0], 0)
        self.stage(path, 'verification')
        self.assertEqual(self.call('verify', 'run', '--root', str(root), '--packet', str(path), '--check-id', 'boundary')[0], 0)
        self.stage(path, 'ownership')
        receipt = json.loads(path.read_text())['verification']['receipts'][0]
        self.assertEqual(receipt['head_sha'], self.git(root, 'rev-parse', 'HEAD'))
        self.assertEqual(receipt['integrity_status'], 'stable')
        self.assertEqual(receipt['provenance'], 'contributor_local')
        source.write_text(json.dumps(valid_packet()['ownership']))
        self.assertEqual(self.call('packet', 'ownership', 'record', '--packet', str(path), '--input', str(source))[0], 0)
        self.stage(path, 'narrative')
        source.write_text(json.dumps(valid_packet()['ai_assistance']))
        self.assertEqual(self.call('packet', 'ai', 'record', '--packet', str(path), '--input', str(source))[0], 0)
        self.stage(path, 'narrative')
        body = path.parent / 'body.md'
        body.write_text(ISSUE + '\nFix the bounded failure.\n' + valid_packet()['ai_assistance']['disclosure']['text'] + '\n')
        self.assertEqual(self.call('packet', 'narrative', 'record', '--packet', str(path), '--title', 'Fix boundary', '--body-file', str(body))[0], 0)
        self.stage(path, 'narrative')
        self.assertEqual(self.call('packet', 'narrative', 'preview', '--packet', str(path))[1]['confirmation_blockers'], [])
        self.assertEqual(self.call('packet', 'narrative', 'confirm', '--packet', str(path), '--human-confirmed')[0], 0)
        self.stage(path, 'ready')
        remote_args = ('remote', 'plan', '--root', str(root), '--packet', str(path), '--repo', 'example/project',
                       '--kind', 'pull_request', '--title', 'Fix boundary', '--body-file', str(body), '--base', 'main', '--head', 'contribution')
        with patch('reviewworthy.cli.GhClient') as provider:
            before = path.read_bytes()
            code, planned = self.call(*remote_args)
            self.assertEqual(code, 0, planned)
            self.assertEqual(planned['readiness_blockers'], [])
            self.assertEqual(self.call('status', '--packet', str(path))[0], 0)
            self.stage(path, 'ready')
            self.assertEqual(path.read_bytes(), before)
            provider.assert_not_called()
        self.assertEqual(self.git(root, 'status', '--porcelain'), '')
        self.assertEqual(len(transport.calls), 2)
        return path, source, remote_args

    def test_python_node_and_go_shapes_complete_without_packet_edits_or_provider_writes(self) -> None:
        for shape in ('python', 'node', 'go'):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as directory:
                self.journey(Path(directory), shape)

    def test_material_changes_route_back_after_approval_verification_and_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, source, args = self.journey(root, 'python')
            packet = json.loads(path.read_text())
            # Re-recording identical decisions and an audit-only receipt preserves readiness.
            source.write_text(json.dumps(packet['verification']['plan']))
            self.assertEqual(self.call('packet', 'verification', 'plan', '--packet', str(path), '--input', str(source))[0], 0)
            self.assertEqual(self.call('verify', 'run', '--root', str(root), '--packet', str(path), '--check-id', 'boundary')[0], 0)
            self.stage(path, 'ready')
            body = Path(args[args.index('--body-file') + 1])
            body.write_text(body.read_text() + 'Clarify risk.\n')
            self.assertEqual(self.call('packet', 'narrative', 'record', '--packet', str(path), '--title', 'Fix boundary', '--body-file', str(body))[0], 0)
            self.stage(path, 'narrative')
            self.assertFalse(json.loads(path.read_text())['narrative']['final_preview_confirmed'])
            (root / 'src/boundary.py').write_text('value = 2\n# changed subject\n')
            self.git(root, 'commit', '-qam', 'changed subject')
            self.assertEqual(self.call('diff', 'bind', '--root', str(root), '--packet', str(path), '--base', 'main', '--head', 'HEAD')[0], 0)
            self.stage(path, 'verification')
            changed = json.loads(path.read_text())
            self.assertEqual(changed['verification']['receipts'], [])
            self.assertEqual(changed['ownership']['status'], 'not_run')
            self.assertFalse(changed['narrative']['final_preview_confirmed'])
            plan = packet['verification']['plan']
            plan['checks'][0]['argv'][-1] += '; print("changed plan")'
            source.write_text(json.dumps(plan))
            self.assertEqual(self.call('packet', 'verification', 'plan', '--packet', str(path), '--input', str(source))[0], 0)
            self.stage(path, 'verification')
            self.assertEqual(json.loads(path.read_text())['verification']['receipts'], [])
            contract = packet['contract']
            contract['design'] = 'A materially changed boundary design'
            source.write_text(json.dumps(contract))
            self.assertEqual(self.call('packet', 'contract', 'bind', '--packet', str(path), '--contract', str(source))[0], 0)
            self.stage(path, 'contract')
            current = json.loads(path.read_text())
            self.assertFalse(current['contract']['approval']['human_confirmed'])
            self.assertEqual(current['diff']['head_sha'], '')

    def test_pending_operation_next_and_recovery_use_saved_original_without_remote_write(self) -> None:
        import shlex
        from unittest.mock import patch
        from reviewworthy.github import GhClient, operation_receipt_path, save_operation_pending
        from test_onboarding import ReadOnlyTransport
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, source, args = self.journey(root, 'python')
            packet = json.loads(path.read_text())
            operation = build_operation(packet, 'example/project', 'pull_request', packet['narrative']['title'],
                                        packet['narrative']['body'], 'main', 'contribution', packet['diff'])
            state = operation_receipt_path(path, operation.operation_id)
            save_operation_pending(state, operation)
            before = path.read_bytes()
            next_action = self.stage(path, 'ready')['next'][0]
            self.assertIn('remote reconcile', next_action['command'])
            url = 'https://github.com/example/project/pull/7'
            class RecoveryTransport(ReadOnlyTransport):
                def __call__(self, argv, **kwargs):
                    if 'repos/example/project/issues' in argv:
                        self.calls.append(argv)
                        result = [{'html_url': url, 'pull_request': {}, 'title': operation.title, 'body': operation.body}]
                    elif 'repos/example/project/pulls/7' in argv:
                        self.calls.append(argv)
                        result = {'html_url': url, 'title': operation.title, 'body': operation.body,
                                  'head': {'sha': operation.head_sha}, 'base': {'ref': operation.base}, 'draft': operation.draft}
                    elif 'repos/example/project/issues/1/comments' in argv:
                        self.calls.append(argv)
                        result = [[{'body': url}]]
                    else:
                        return super().__call__(argv, **kwargs)
                    self.assert_read_only(argv)
                    return subprocess.CompletedProcess(argv, 0, json.dumps(result), '')

                def assert_read_only(self, argv):
                    if argv[argv.index('--method') + 1] != 'GET':
                        raise AssertionError(argv)
            transport = RecoveryTransport()
            with patch('reviewworthy.cli.GhClient', side_effect=lambda: GhClient(transport)):
                code, recovered = self.call(*shlex.split(next_action['command'])[1:-1])
            self.assertEqual(code, 0, recovered)
            self.assertEqual(recovered['status'], 'linked')
            self.assertEqual(json.loads(state.read_text())['status'], 'linked')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(self.stage(path, 'ready')['next'][0]['kind'], 'decision')
