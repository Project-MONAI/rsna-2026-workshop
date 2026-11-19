"""HTTP regression checks for the curated experiment and inference roots."""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urljoin
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webui"))
import app


class ViewerRootsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.challenge = self.root / "challenge"
        self.inference = self.root / "inference_tmp"
        (self.challenge / "task").mkdir(parents=True)
        (self.inference / "case 1").mkdir(parents=True)
        (self.challenge / "task/report.md").write_text("# Experiment report")
        case = self.inference / "case 1"
        (case / "README.md").write_text("# Inference\n\n[Case](result_viewer.html)\n\n![Preview](slice.png)\n\n[Notes](notes.md)")
        (case / "notes.md").write_text("# Notes")
        (case / "result_viewer.html").write_text('<img src="slice.png"><a href="../../../nii?images=files/inference_tmp/case%201/image.nii.gz">Overlay</a>')
        (case / "slice.png").write_bytes(b"image fixture")
        (case / "image.nii.gz").write_bytes(b"volume fixture")
        (self.root / ".env").write_text("PRIVATE=not-visible")
        (self.root / "unrelated").mkdir()
        (self.root / "unrelated/secret.txt").write_text("not-visible")
        (case / "escape").symlink_to(self.root / "unrelated", target_is_directory=True)
        handler = type("TestHandler", (app.WebUIHandler,), {
            "files_dir": self.challenge, "challenge_dir": self.challenge,
            "inference_dir": self.inference, "data_dir": None,
            "niivue_root": None, "runtime_dir": self.root / "runtime",
            "start_at_root": True, "log_message": lambda *args: None,
        })
        self.server = app.ReusableThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def get(self, path):
        with urlopen(self.base + path, timeout=5) as response:
            return response.read()

    def test_only_two_curated_roots_are_listed(self):
        tree = json.loads(self.get("/api/tree"))
        self.assertEqual([node["name"] for node in tree["tree"]], ["challenge", "inference_tmp"])
        self.assertTrue(all(node["name"] == node["path"] for node in tree["tree"]))
        self.assertTrue(tree["start_at_root"])
        self.assertTrue(tree["multiple_roots"])
        self.assertNotIn("secret.txt", json.dumps(tree))
        self.assertNotIn('"escape"', json.dumps(tree))
        self.assertNotIn('".env"', json.dumps(tree))
        self.assertEqual(tree["tree"][1]["children"][0]["path"], "inference_tmp/case 1")

    def test_new_and_legacy_experiment_urls_work(self):
        for path in ("challenge/task/report.md", "task/report.md"):
            with self.subTest(path=path):
                self.assertIn(b"Experiment report", self.get("/files/" + path))
                self.assertIn(b"Experiment report", self.get("/md?path=" + quote(path)))

    def test_inference_html_and_relative_assets_work(self):
        path = "/files/inference_tmp/case%201/result_viewer.html"
        self.assertIn(b"slice.png", self.get(path))
        asset = urljoin(path, "slice.png")
        self.assertEqual(self.get(asset), b"image fixture")
        self.assertEqual(self.get("/files/inference_tmp/case%201/image.nii.gz"), b"volume fixture")
        self.assertEqual(urljoin(path, "../../../nii"), "/nii")

    def test_markdown_keeps_links_in_the_inference_namespace(self):
        page = self.get("/md?path=" + quote("inference_tmp/case 1/README.md")).decode()
        self.assertIn('href="files/inference_tmp/case%201/result_viewer.html"', page)
        self.assertIn('src="files/inference_tmp/case%201/slice.png"', page)
        self.assertIn('href="md?path=inference_tmp/case%201/notes.md"', page)
        self.assertEqual(self.get("/api/raw?path=" + quote("inference_tmp/case 1/notes.md")), b"# Notes")
        self.assertIn(b"Notes", self.get("/view?path=" + quote("inference_tmp/case 1/notes.md")))
        self.assertEqual(self.get("/asset?path=" + quote("inference_tmp/case 1/slice.png")), b"image fixture")

    def test_path_and_symlink_escapes_are_rejected(self):
        for path in ("../.env", "inference_tmp/../.env", "challenge/../.env",
                     "inference_tmp/case 1/escape/secret.txt", "inference_tmp/%2e%2e/.env"):
            for endpoint in ("/api/raw?path=", "/md?path=", "/view?path=", "/asset?path="):
                with self.subTest(path=path, endpoint=endpoint), self.assertRaises(HTTPError) as error:
                    self.get(endpoint + quote(path))
                self.assertEqual(error.exception.code, 404)
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                self.get("/files/" + quote(path, safe="/"))
            self.assertEqual(error.exception.code, 404)

    def test_missing_inference_root_is_empty_until_outputs_arrive(self):
        missing = self.root / "future_outputs"
        tree = app.build_browser_tree(self.challenge, missing)
        self.assertEqual(tree["tree"][1]["children"], [])
        (missing / "new_case").mkdir(parents=True)
        (missing / "new_case/result.json").write_text("{}")
        tree = app.build_browser_tree(self.challenge, missing)
        self.assertEqual(tree["tree"][1]["children"][0]["name"], "new_case")

    def test_single_root_viewers_are_unchanged(self):
        self.assertEqual(app.build_browser_tree(self.challenge, None), app.build_file_tree(self.challenge))

    def test_static_routes_cannot_escape_the_asset_directory(self):
        with self.assertRaises(HTTPError) as error:
            self.get("/static/%2e%2e/app.py")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
