import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_data_prep


class ContainerPreparationTests(unittest.TestCase):
    def test_separate_from_compose_and_restricted_mounts(self):
        build, command = run_data_prep.container_commands(['docker'], Path('/tmp/raw'), Path('/tmp/data'),
                                                         'all', 'both', 2, 'preserve')
        self.assertEqual(build[:2], ['docker', 'build'])
        self.assertEqual(command[:2], ['docker', 'run'])
        self.assertNotIn('compose', command)
        self.assertNotIn('--gpus', command)
        self.assertNotIn('/var/run/docker.sock', ' '.join(command))
        self.assertIn('type=bind,source=/tmp/raw,target=/raw', command)
        self.assertIn('type=bind,source=/tmp/data,target=/data', command)
        self.assertIn(f'{os.getuid()}:{os.getgid()}', command)
        self.assertIn('--rm', command)

    def test_plan_creates_no_directories_or_subprocesses(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / 'raw'
            data = Path(d) / 'data'
            with patch('sys.argv', ['run_data_prep.py', '--plan', '--raw-dir', str(raw), '--output-dir', str(data)]), \
                 patch('subprocess.run') as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_data_prep.main(), 0)
            run.assert_not_called()
            self.assertFalse(raw.exists())
            self.assertFalse(data.exists())

    def test_default_policy_is_background(self):
        with patch('sys.argv', ['run_data_prep.py', '--plan']), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            run_data_prep.main()
        self.assertIn('--unknown-labels background', output.getvalue())

    def test_build_precedes_run_and_secrets_are_not_forwarded(self):
        with tempfile.TemporaryDirectory() as d:
            command = ['run_data_prep.py', '--raw-dir', d + '/raw', '--output-dir', d + '/data', '--unknown-labels', 'preserve']
            with patch('sys.argv', command), patch.dict(os.environ, {'GITHUB_TOKEN': 'test', 'MIAgent_GATEWAY_PASSWORD': 'test'}), \
                 patch('subprocess.run') as run:
                self.assertEqual(run_data_prep.main(), 0)
            calls = run.call_args_list
            self.assertEqual(calls[1].args[0][1], 'build')
            self.assertEqual(calls[2].args[0][1], 'run')
            for call in calls:
                self.assertNotIn('GITHUB_TOKEN', call.kwargs['env'])
                self.assertNotIn('MIAgent_GATEWAY_PASSWORD', call.kwargs['env'])

    def test_failed_build_does_not_start_container(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('sys.argv', ['run_data_prep.py', '--raw-dir', d + '/raw', '--output-dir', d + '/data']), \
                 patch('subprocess.run', side_effect=[None, subprocess.CalledProcessError(1, ['docker', 'build'])]) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    run_data_prep.main()
                self.assertEqual(run.call_count, 2)

    def test_sudo_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('sys.argv', ['run_data_prep.py', '--raw-dir', d + '/raw', '--output-dir', d + '/data']), \
                 patch('subprocess.run', side_effect=[subprocess.CalledProcessError(1, ['docker', 'info']), None, None, None]) as run:
                run_data_prep.main()
            for call in run.call_args_list[1:]:
                self.assertEqual(call.args[0][:3], ['sudo', '-n', 'docker'])

    def test_nested_mounts_rejected(self):
        with patch('sys.argv', ['run_data_prep.py', '--plan', '--raw-dir', '/tmp/data/raw', '--output-dir', '/tmp/data']), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                run_data_prep.main()


if __name__ == '__main__':
    unittest.main()
