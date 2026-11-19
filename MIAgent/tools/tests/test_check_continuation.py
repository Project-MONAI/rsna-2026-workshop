from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module() -> object:
    path = Path(__file__).resolve().parents[1] / "check_continuation.py"
    spec = importlib.util.spec_from_file_location("check_continuation", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_accepts_matching_live_job(tmp_path: Path) -> None:
    check = load_module()
    dashboard = tmp_path / "dashboard.md"
    state = tmp_path / "state.md"
    run = tmp_path / "baselines" / "base" / "runs" / "exp001"; run.mkdir(parents=True)
    (run / "job.json").write_text('{"experiment":"exp001","state":"queued"}')
    dashboard.write_text("""| Run state | active |
<!-- next-concrete-action: begin -->
Run exp001.
<!-- next-concrete-action: end -->
<!-- continuation-contract: begin -->
| Field | Current durable record |
|---|---|
| Evidence reviewed | design |
| Current decision | smoke first |
| Next concrete action | Run exp001 |
| Owner | scheduler |
| Next monitoring time | on dispatch |
| Disposition | active/queued job |
<!-- continuation-contract: end -->
""")
    state.write_text("<!-- current-decision-record: begin -->\nEvidence supports exp001.\n<!-- current-decision-record: end -->\n")
    assert check.check(tmp_path)["ok"]


def test_check_rejects_missing_contract(tmp_path: Path) -> None:
    check = load_module()
    (tmp_path / "dashboard.md").write_text("<!-- next-concrete-action: begin -->\nDo work.\n<!-- next-concrete-action: end -->\n")
    (tmp_path / "state.md").write_text("state")
    result = check.check(tmp_path)
    assert not result["ok"]
    assert any("Continuation Contract" in error for error in result["errors"])
