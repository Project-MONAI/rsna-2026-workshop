"""Resolve the real Compose configuration without starting any containers."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('docker'), 'Docker CLI is not installed')
class PaseoConfigTests(unittest.TestCase):
    def test_brev_hostnames_are_allowed_without_instance_parameter(self):
        repo = Path(__file__).resolve().parent.parent / 'MIAgent'
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('MIAgent_', 'COMPOSE_'))}
        result = subprocess.run(['docker', 'compose', '--env-file', '.env.example',
                                 'config', '--format', 'json'], cwd=repo, env=env,
                                text=True, capture_output=True, check=True)
        config = json.loads(result.stdout)
        paseo = config['services']['paseo']
        hosts = paseo['environment']['PASEO_HOSTNAMES'].split(',')
        self.assertIn('.brevlab.com', hosts)
        self.assertIn('.gobrev.dev', hosts)
        self.assertIn('localhost', hosts)
        self.assertNotIn('true', hosts)
        self.assertNotIn('*', hosts)
        self.assertFalse(paseo.get('ports'))


if __name__ == '__main__':
    unittest.main()
