import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


source = Path(__file__).resolve().parent.parent / "MIAgent/containers/paseo/patch_file_tabs.py"
spec = importlib.util.spec_from_file_location("paseo_file_tabs", source)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class FileTabsTests(unittest.TestCase):
    def fixture(self, root, version="0.9.2", bundle=None):
        package = Path(root)
        (package / "package.json").write_text(json.dumps({"version": version}))
        ui = package / "dist/server/web-ui"
        assets = ui / "_expo/static/js/web"
        assets.mkdir(parents=True)
        (ui / "index.html").write_text('<script src="/_expo/static/js/web/index-test.js"></script>')
        (assets / "index-test.js").write_text(bundle or patch.BEFORE)
        return package, ui, assets

    def test_new_cached_asset_matches_compressed_asset_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            package, ui, assets = self.fixture(root)
            patch.patch_ui(package)
            target = assets / "index-test.miagent-tabs-v1.js"
            self.assertEqual(target.read_text(), patch.AFTER)
            self.assertEqual(gzip.decompress(target.with_suffix(".js.gz").read_bytes()), target.read_bytes())
            self.assertIn(target.name, (ui / "index.html").read_text())
            self.assertEqual((assets / "index-test.js").read_text(), patch.BEFORE)
            patch.patch_ui(package)
            self.assertEqual(target.read_text(), patch.AFTER)

    def test_unknown_versions_and_changed_bundles_fail_before_index_changes(self):
        for version, bundle in [("0.13.1", patch.BEFORE), ("0.9.2", "changed vendor code")]:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as root:
                package, ui, _ = self.fixture(root, version, bundle)
                original = (ui / "index.html").read_bytes()
                with self.assertRaises(RuntimeError):
                    patch.patch_ui(package)
                self.assertEqual((ui / "index.html").read_bytes(), original)
