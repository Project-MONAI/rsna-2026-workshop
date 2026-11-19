import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest

import prepare_nvsegment


class LauncherTests(unittest.TestCase):
    def launch(self, running=False, exited=False):
        calls = []
        info = {'Name': '/miagent-training-1', 'Image': 'sha256:prepared-training-image',
                'Config': {'User': '1000:1000'}, 'Mounts': [
                    {'Type': 'volume', 'Name': 'custom-workspace', 'Destination': '/workspace'},
                    {'Type': 'volume', 'Name': 'custom-cache', 'Destination': '/cache'},
                    {'Type': 'bind', 'Source': '/data', 'Destination': '/data'}]}
        def runner(command, **kwargs):
            calls.append(command)
            if 'compose' in command:
                output = 'training-id'
            elif 'ps' in command:
                output = 'previous-id' if running or exited else ''
            elif 'inspect' in command:
                output = json.dumps([{'State': {'Running': running}}] if command[-1] == 'previous-id' else [info])
            else:
                output = ''
            return subprocess.CompletedProcess(command, 0, stdout=output)
        with contextlib.redirect_stdout(io.StringIO()):
            name = prepare_nvsegment.start_preparation(['docker'], Path('/repo'), {}, runner)
        return name, calls

    def test_standalone_gpu_free_container_with_only_required_mounts(self):
        name, calls = self.launch()
        command = next(c for c in calls if 'run' in c)
        self.assertIn('--detach', command)
        self.assertEqual(command[command.index('--pull') + 1], 'never')
        self.assertNotIn('compose', command)
        self.assertNotIn('--gpus', command)
        self.assertNotIn('--privileged', command)
        mounts = [command[i + 1] for i, value in enumerate(command) if value == '--mount']
        self.assertEqual(mounts, ['type=volume,source=custom-workspace,target=/workspace,readonly',
                                  'type=volume,source=custom-cache,target=/cache'])
        self.assertIn('CUDA_VISIBLE_DEVICES=', command)
        self.assertIn('NVIDIA_VISIBLE_DEVICES=void', command)
        self.assertEqual(command[-2:], ['sha256:prepared-training-image', '/workspace/tools/prepare_lab_models.py'])
        self.assertEqual(name, 'miagent-training-1-nvsegment-prepare')

    def test_running_preparation_is_not_duplicated(self):
        _, calls = self.launch(running=True)
        self.assertFalse(any('run' in c or 'rm' in c for c in calls))

    def test_completed_or_failed_container_can_be_retried(self):
        _, calls = self.launch(exited=True)
        self.assertIn(['docker', 'rm', 'previous-id'], calls)
        self.assertTrue(any('run' in c for c in calls))


if __name__ == '__main__':
    unittest.main()
