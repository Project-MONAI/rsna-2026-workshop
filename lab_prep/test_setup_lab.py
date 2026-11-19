import contextlib
import io
import json
import os
import shutil
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import setup_lab
import prepare_nvsegment


class SetupTests(unittest.TestCase):
    def test_environment_removes_obsolete_gateway_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('MIAgent_GATEWAY_USERNAME=old-user\nMIAgent_GATEWAY_PASSWORD=old-password\nMIAgent_HTTP_PORT=8088\n')
            setup_lab.update_env(path, path, {})
            self.assertNotIn('GATEWAY_USERNAME', path.read_text())
            self.assertNotIn('GATEWAY_PASSWORD', path.read_text())
            self.assertIn('MIAgent_HTTP_PORT=8088', path.read_text())

    def test_gateway_has_no_secondary_login(self):
        repo = Path(__file__).resolve().parent.parent / 'MIAgent'
        nginx = (repo / 'containers/gateway/default.conf.template').read_text()
        self.assertIn('auth_basic off;', nginx)
        self.assertNotIn('auth_basic_user_file', nginx)
        self.assertNotIn('htpasswd', (repo / 'containers/gateway/Dockerfile').read_text())
        self.assertNotIn('MIAgent_GATEWAY_PASSWORD=', (repo / '.env.example').read_text())
        self.assertIn('<h3>Open WebUI</h3>', (repo / 'containers/gateway/index.html').read_text())
        self.assertIn('ghcr.io/open-webui/open-webui:', (repo / 'docker-compose.yml').read_text())
        self.assertIn('WEBUI_AUTH: "False"', (repo / 'docker-compose.yml').read_text())

    def test_plan_has_no_side_effects(self):
        with patch('sys.argv', ['setup_lab.py', '--plan']), patch.object(setup_lab, 'run') as run:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(setup_lab.main(), 0)
            run.assert_not_called()
            self.assertIn('Download pinned Qwen', output.getvalue())

    def test_env_preserves_existing_settings(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / '.env'
            path.write_text('# comment\nMIAgent_HTTP_PORT=9999\nLOCAL_UID=123\n')
            setup_lab.update_env(path, Path(d) / 'missing', {'LOCAL_UID': '1000'})
            self.assertIn('MIAgent_HTTP_PORT=9999', path.read_text())
            self.assertIn('LOCAL_UID=1000', path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_clone_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            setup_lab.clone_repo('https://secret@github.com/owner/repo.git', Path('/tmp/no-clone'), None, {})

    def test_clone_credentials_not_in_arguments(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(setup_lab, 'run') as run:
                setup_lab.clone_repo('https://github.com/owner/repo.git', Path(d) / 'repo', 'main', {'GITHUB_TOKEN': 'example-token'})
            command = run.call_args.args[0]
            self.assertNotIn('example-token', ' '.join(command))
            self.assertEqual(run.call_args.kwargs['env']['MIAgent_CLONE_TOKEN'], 'example-token')
            self.assertFalse(Path(run.call_args.kwargs['env']['GIT_ASKPASS']).exists())

    def test_missing_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                setup_lab.validate_data(Path(d))

    def test_preparation_requires_explicit_policy(self):
        with patch('sys.argv', ['setup_lab.py', '--plan', '--prepare-data']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                setup_lab.main()

    def test_active_lab_is_not_changed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'MIAgent').mkdir()
            (root / 'MIAgent/docker-compose.yml').touch()
            def result(command, **kwargs):
                return setup_lab.subprocess.CompletedProcess(command, 0, stdout='container-id' if 'ps' in command else '')
            with patch('sys.argv', ['setup_lab.py', '--root', str(root)]), patch.object(setup_lab, 'run', side_effect=result) as run:
                with self.assertRaisesRegex(ValueError, 'active lab'):
                    setup_lab.main()
                self.assertFalse((root / 'MIAgent/.env').exists())
                self.assertFalse(any('up' in c.args[0] or 'build' in c.args[0] for c in run.call_args_list))

    def test_stage_order_and_token_scrubbing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / 'MIAgent'
            (repo / 'containers/gateway').mkdir(parents=True)
            (repo / 'docker-compose.yml').touch()
            (repo / '.env.example').write_text('MIAgent_HTTP_PORT=8088\n')
            calls = []
            def result(command, **kwargs):
                calls.append(command)
                self.assertNotIn('GITHUB_TOKEN', kwargs['env'])
                if 'compose' in command and shutil.which('docker'):
                    # Validate the actual CLI grammar without contacting Docker
                    # or starting containers; mocks alone miss invalid flags.
                    check = list(command)
                    if 'run' in check:
                        check.insert(check.index('run') + 1, '--help')
                    elif 'exec' in check:
                        check.insert(check.index('exec') + 1, '--help')
                    else:
                        check.append('--help')
                    parsed = setup_lab.subprocess.run(check, capture_output=True, text=True)
                    self.assertEqual(parsed.returncode, 0, parsed.stderr)
                self.assertNotEqual(command[0], 'openssl')
                return setup_lab.subprocess.CompletedProcess(command, 0, stdout='')
            with patch('sys.argv', ['setup_lab.py', '--root', str(root), '--prepare-data',
                                    '--spacing-mm', '2', '--unknown-labels', 'preserve']), \
                 patch.dict(os.environ, {'GITHUB_TOKEN': 'test-secret'}), \
                 patch.object(setup_lab, 'run', side_effect=result), \
                 patch.object(setup_lab, 'validate_data'), \
                 patch.object(Path, 'stat', autospec=True) as stat:
                # Use real file stats except for the Docker socket.
                real_stat = os.stat
                stat.side_effect = lambda path, **kw: type('Stat', (), {'st_gid': 983})() if str(path) == '/var/run/docker.sock' else real_stat(path, **kw)
                with contextlib.redirect_stdout(io.StringIO()):
                    setup_lab.main()
            self.assertFalse((repo / 'containers/gateway/htpasswd').exists())
            self.assertNotIn('MIAgent_GATEWAY_PASSWORD=', (repo / '.env').read_text())
            download = next(i for i,c in enumerate(calls) if 'llm-download' in c and 'run' in c)
            preparation = next(i for i,c in enumerate(calls) if str(root / 'lab_prep/run_data_prep.py') in c)
            init = next(i for i,c in enumerate(calls) if 'lab-init' in c and 'up' in c)
            llm = next(i for i,c in enumerate(calls) if 'llm' in c and 'up' in c)
            self.assertFalse(any('/workspace/tools/prepare_lab_models.py' in c for c in calls))
            gateway = next(i for i,c in enumerate(calls) if 'gateway' in c and 'up' in c)
            inference = next(i for i,c in enumerate(calls) if str(root / 'lab_prep/prepare_nvsegment.py') in c)
            self.assertLess(gateway, inference)
            self.assertIn('--background', calls[inference])
            self.assertLess(preparation, init)
            self.assertFalse(any('venv' in c or 'pip' in c or 'apt-get' in c for c in calls))
            self.assertLess(download, init)
            self.assertLess(init, gateway)
            self.assertLess(llm, gateway)
            report = json.loads((root / 'build_reports/startup_timing.json').read_text())
            self.assertEqual(report['status'], 'complete')
            self.assertGreaterEqual(report['total_seconds'], 0)
            self.assertTrue(all(s['status'] == 'complete' for s in report['stages']))
            for command in calls:
                if 'up' in command:
                    self.assertIn('--no-build', command)

    def test_parallel_tasks_overlap(self):
        barrier = threading.Barrier(4)
        def task():
            barrier.wait(timeout=3)
        with contextlib.redirect_stdout(io.StringIO()):
            timings = setup_lab.Timings()
            setup_lab.parallel_tasks(timings, [(str(i), task) for i in range(4)])
        self.assertEqual(len(timings.records), 4)
        self.assertTrue(all(r['status'] == 'complete' for r in timings.records))

    def test_background_preparation_failure_does_not_fail_available_lab(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'MIAgent'
            repo.mkdir()
            (repo / 'docker-compose.yml').touch()
            (repo / '.env.example').write_text('MIAgent_HTTP_PORT=8088\n')
            def result(command, **kwargs):
                if str(root / 'lab_prep/prepare_nvsegment.py') in command:
                    raise setup_lab.subprocess.CalledProcessError(1, command)
                return setup_lab.subprocess.CompletedProcess(command, 0, stdout='')
            real_stat = os.stat
            def stat(path, **kwargs):
                return type('Stat', (), {'st_gid': 983})() if str(path) == '/var/run/docker.sock' else real_stat(path, **kwargs)
            with patch('sys.argv', ['setup_lab.py', '--root', str(root)]), \
                 patch.object(setup_lab, 'run', side_effect=result), \
                 patch.object(setup_lab, 'validate_data'), \
                 patch.object(Path, 'stat', autospec=True, side_effect=stat), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(setup_lab.main(), 0)
            report = json.loads((root / 'build_reports/startup_timing.json').read_text())
            self.assertEqual(report['status'], 'complete')
            self.assertTrue(any(stage['status'] == 'failed' and stage['stage'] == 'Start background NV-Segment preparation'
                                for stage in report['stages']))

    def test_download_failure_prevents_service_startup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / 'MIAgent'
            (repo / 'containers/gateway').mkdir(parents=True)
            (repo / 'docker-compose.yml').touch()
            (repo / '.env.example').write_text('MIAgent_HTTP_PORT=8088\n')
            calls = []
            def result(command, **kwargs):
                calls.append(command)
                if 'llm-download' in command and 'run' in command:
                    raise setup_lab.subprocess.CalledProcessError(1, command)
                return setup_lab.subprocess.CompletedProcess(command, 0, stdout='')
            real_stat = os.stat
            def stat(path, **kwargs):
                return type('Stat', (), {'st_gid': 983})() if str(path) == '/var/run/docker.sock' else real_stat(path, **kwargs)
            with patch('sys.argv', ['setup_lab.py', '--root', str(root)]), \
                 patch.object(setup_lab, 'run', side_effect=result), \
                 patch.object(setup_lab, 'validate_data'), \
                 patch.object(Path, 'stat', autospec=True, side_effect=stat), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(setup_lab.subprocess.CalledProcessError):
                    setup_lab.main()
            self.assertFalse(any('up' in c for c in calls))
            report = json.loads((root / 'build_reports/startup_timing.json').read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertTrue(any(s['stage'] == 'Download Qwen model' and s['status'] == 'failed'
                                for s in report['stages']))

    def test_parallel_failure_is_reported_and_workers_are_joined(self):
        barrier = threading.Barrier(2)
        finished = threading.Event()
        def fail():
            barrier.wait(timeout=3)
            raise ValueError('download failed')
        def finish():
            barrier.wait(timeout=3)
            finished.set()
        with contextlib.redirect_stdout(io.StringIO()):
            timings = setup_lab.Timings()
            with self.assertRaisesRegex(ValueError, 'download failed'):
                setup_lab.parallel_tasks(timings, [('bad', fail), ('good', finish)])
        self.assertTrue(finished.is_set())
        self.assertEqual(next(r['status'] for r in timings.records if r['stage'] == 'bad'), 'failed')

    def test_optional_bundle_launches_background_without_waiting(self):
        with patch('sys.argv', ['prepare_nvsegment.py', '--background']), \
             patch.object(prepare_nvsegment, 'run') as run, \
             patch.object(prepare_nvsegment, 'start_preparation', return_value='prep-container') as launch:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(prepare_nvsegment.main(), 0)
        launch.assert_called_once()
        self.assertFalse(any('wait' in c.args[0] or 'logs' in c.args[0] for c in run.call_args_list))


if __name__ == '__main__':
    unittest.main()
