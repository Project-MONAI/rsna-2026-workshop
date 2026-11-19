import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parent.parent / 'MIAgent/containers/paseo/configure_local_provider.py'
spec = importlib.util.spec_from_file_location('paseo_provider', path)
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


class ProviderTests(unittest.TestCase):
    def test_local_qwen_default_and_existing_settings_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_path = home / '.paseo/config.json'
            config_path.parent.mkdir()
            config_path.write_text(json.dumps({'version': 1, 'app': {'baseUrl': 'custom'},
                                               'agents': {'providers': {'codex': {'enabled': True}}}}))
            with patch.dict(os.environ, {'HOME': directory, 'PASEO_HOME': str(config_path.parent),
                                         'OPENCODE_MODEL': 'miagent-llm/Qwen/Qwen3.8-27B-FP8'}):
                provider.configure()
                provider.configure()
            config = json.loads(config_path.read_text())
            self.assertEqual(config['app']['baseUrl'], 'custom')
            providers = config['agents']['providers']
            self.assertFalse(providers['codex']['enabled'])
            self.assertTrue(providers['opencode']['enabled'])
            self.assertTrue(providers['opencode']['models'][0]['isDefault'])
            self.assertEqual(providers['opencode']['models'][0]['id'], 'miagent-llm/Qwen/Qwen3.8-27B-FP8')
            self.assertEqual(providers['opencode']['env']['OPENCODE_CONFIG'], '/workspace/opencode.json')
