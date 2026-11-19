import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class BrevStartupTests(unittest.TestCase):
    def setUp(self):
        script = Path(__file__).with_name("brev_startup.sh").read_text()
        source = script.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        self.scope = {"__name__": "startup_tests"}
        exec(compile(source, "brev_startup.sh", "exec"), self.scope)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "existing checkout"
        (self.root / "lab_prep").mkdir(parents=True)
        (self.root / "MIAgent").mkdir()
        (self.root / "lab_prep/setup_lab.py").touch()
        (self.root / "MIAgent/docker-compose.yml").touch()

    def invoke(self, overrides=None):
        env = {"MIAgent_LAB_ROOT": str(self.root), **(overrides or {})}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(self.scope["subprocess"], "run") as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.scope["main"]()
        return run

    def test_existing_checkout_needs_no_github_token_or_second_clone(self):
        run = self.invoke()
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[1], str(self.root / "lab_prep/setup_lab.py"))
        self.assertNotIn("--repo-url", command)
        self.assertNotIn("git", command)
        self.assertEqual(run.call_args.kwargs["cwd"], self.root)
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(command[command.index("--root") + 1], str(self.root))

    def test_fresh_workshop_prepares_two_mm_data_with_explicit_label_policy(self):
        command = self.invoke().call_args.args[0]
        self.assertIn("--prepare-data", command)
        self.assertEqual(command[command.index("--spacing-mm") + 1], "2")
        self.assertEqual(command[command.index("--unknown-labels") + 1], "background")

    def test_existing_data_opt_out(self):
        command = self.invoke({"MIAgent_PREPARE_DATA": "false"}).call_args.args[0]
        self.assertNotIn("--prepare-data", command)

    def test_operator_can_select_data_policy(self):
        command = self.invoke({"MIAgent_DATA_SPACING_MM": "1", "MIAgent_UNKNOWN_LABELS": "error"}).call_args.args[0]
        self.assertEqual(command[command.index("--spacing-mm") + 1], "1")
        self.assertEqual(command[command.index("--unknown-labels") + 1], "error")

    def test_invalid_data_flag_fails_before_setup(self):
        with self.assertRaisesRegex(SystemExit, "true or false"):
            self.invoke({"MIAgent_PREPARE_DATA": "maybe"})

    def test_explicit_missing_checkout_is_not_replaced_or_cloned(self):
        with self.assertRaisesRegex(SystemExit, "does not clone"):
            self.invoke({"MIAgent_LAB_ROOT": str(self.root / "missing")})
        self.assertFalse((self.root / "missing").exists())

    def test_brev_working_directory_can_supply_checkout(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(self.scope["Path"], "cwd", return_value=self.root), \
             patch.object(self.scope["subprocess"], "run") as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.scope["main"]()
        self.assertEqual(run.call_args.kwargs["cwd"], self.root)


if __name__ == "__main__":
    unittest.main()
