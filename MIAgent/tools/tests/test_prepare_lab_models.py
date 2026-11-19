import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_lab_models as prep


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.weight = b"synthetic checkpoint fixture"
        for name, value in (("WEIGHT_BYTES", len(self.weight)),
                            ("WEIGHT_SHA256", hashlib.sha256(self.weight).hexdigest())):
            patcher = patch.object(prep, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.downloads = []

    def download(self, **kwargs):
        self.downloads.append(kwargs)
        bundle = Path(kwargs['local_dir'])
        for name in kwargs['allow_patterns']:
            target = bundle / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name == prep.WEIGHT:
                target.write_bytes(self.weight)
            elif name == 'metadata.json':
                target.write_text(json.dumps({'network_data_format': {'outputs': {'pred': {
                    'channel_def': {'0': 'background', '1': 'liver', '115': 'heart'}}}}}))
            elif name.endswith('.json'):
                target.write_text('{"fixture": true}')
            else:
                target.write_text('# fixture')

    def prepare(self, downloader=None, validator=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return prep.prepare(self.cache, downloader or self.download, validator or (lambda bundle: None))

    def test_fresh_cache_pinned_download_and_labels(self):
        result = self.prepare()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(prep.model_status(self.cache)['status'], 'ready')
        request = self.downloads[0]
        self.assertEqual(request['revision'], prep.REVISION)
        self.assertEqual([p for p in request['allow_patterns'] if p.endswith('.pt')], [prep.WEIGHT])
        self.assertFalse(any(p.endswith('.safetensors') for p in request['allow_patterns']))
        labels = json.loads((prep.bundle_path(self.cache) / 'label_dict.json').read_text())
        self.assertEqual(labels['heart'], 115)

    def test_prepared_cache_is_reused_offline(self):
        self.prepare()
        with patch.object(prep, 'subprocess') as process:
            self.prepare(downloader=lambda **kw: self.fail('Unexpected download'))
            process.run.assert_not_called()

    def test_legacy_checkpoint_reused_without_copy_or_redownload(self):
        old = self.cache / 'bundles/nv-segment-ct-finetune' / prep.WEIGHT
        old.parent.mkdir(parents=True)
        old.write_bytes(self.weight)
        self.prepare()
        self.assertNotIn(prep.WEIGHT, self.downloads[0]['allow_patterns'])
        self.assertEqual(old.stat().st_ino, (prep.bundle_path(self.cache) / prep.WEIGHT).stat().st_ino)

    def test_download_failure_is_reported_and_retry_works(self):
        def fail(**kwargs):
            raise OSError('network unavailable')
        with self.assertRaisesRegex(OSError, 'network unavailable'):
            self.prepare(downloader=fail)
        self.assertEqual(prep.model_status(self.cache)['status'], 'failed')
        self.assertEqual(self.prepare()['status'], 'ready')

    def test_same_size_bad_checkpoint_is_rejected(self):
        def corrupt(**kwargs):
            self.download(**kwargs)
            (prep.bundle_path(self.cache) / prep.WEIGHT).write_bytes(b'x' * len(self.weight))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.prepare(downloader=corrupt)
        self.assertEqual(prep.model_status(self.cache)['status'], 'failed')

    def test_missing_code_invalidates_ready_status(self):
        self.prepare()
        (prep.bundle_path(self.cache) / 'hugging_face_pipeline.py').unlink()
        self.assertEqual(prep.model_status(self.cache)['status'], 'failed')

    def test_import_validation_failure_does_not_mark_ready(self):
        def fail(bundle):
            raise ImportError('missing runtime dependency')
        with self.assertRaises(ImportError):
            self.prepare(validator=fail)
        self.assertEqual(prep.model_status(self.cache)['status'], 'failed')

    def test_readiness_is_read_only_for_missing_cache(self):
        missing = self.cache / 'not-created'
        self.assertEqual(prep.model_status(missing)['status'], 'not_started')
        self.assertFalse(missing.exists())

    def test_reset_reconnects_cache_without_bundles_in_seed(self):
        script = Path(__file__).resolve().parents[2] / 'containers/lab/init.py'
        spec = importlib.util.spec_from_file_location('lab_init', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        seed, workspace, runtime = (self.cache / name for name in ('seed', 'workspace', 'runtime'))
        for name in ('nv-segment-ct', 'nv-segment-ct-finetune'):
            (seed / 'skills/segmentation' / name).mkdir(parents=True)
        cache = self.cache / 'persistent'
        weight = cache / 'bundles/nv-segment-ct' / prep.WEIGHT
        weight.parent.mkdir(parents=True)
        weight.write_bytes(self.weight)
        marker = self.cache / 'initialized'
        with patch.object(module.os, 'chown'):
            module.initialize(seed, workspace, runtime, cache, marker)
            self.assertEqual((workspace / 'skills/segmentation/nv-segment-ct/bundle').resolve(), cache / 'bundles/nv-segment-ct')
            marker.unlink()
            module.initialize(seed, workspace, runtime, cache, marker)
        self.assertEqual(weight.read_bytes(), self.weight)


if __name__ == '__main__':
    unittest.main()
