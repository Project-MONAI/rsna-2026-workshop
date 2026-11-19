import json
from pathlib import Path

from tools.container_entrypoint import archive_prior_execution


def test_archive_prior_execution_preserves_stage_evidence(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "tracking").mkdir()
    (tmp_path / "run.json").write_text(json.dumps({"return_code": 0, "finished_at": 1_700_000_000}))
    (tmp_path / "logs" / "command.log").write_text("old command\n")
    (tmp_path / "tracking" / "dashboard.json").write_text(json.dumps({"stage": "preprocess"}))
    (tmp_path / "tracking" / "metrics.jsonl").write_text("old metrics\n")
    (tmp_path / "summary.md").write_text("durable scientific summary\n")

    archive = archive_prior_execution(tmp_path)
    assert archive is not None
    assert (archive / "run.json").is_file()
    assert (archive / "logs" / "command.log").read_text() == "old command\n"
    assert (archive / "tracking" / "metrics.jsonl").read_text() == "old metrics\n"
    assert (archive / "summary.md").is_file()
    assert not (tmp_path / "run.json").exists()
    assert not (tmp_path / "tracking" / "metrics.jsonl").exists()
    assert (tmp_path / "summary.md").read_text() == "durable scientific summary\n"
