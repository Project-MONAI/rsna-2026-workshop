from tools.experiment_tracking import _write_live_dice_dashboard


def test_live_dice_dashboard_adds_averages_and_labels(tmp_path):
    tracking = tmp_path / "tracking"
    tracking.mkdir()
    (tracking / "dashboard.md").write_text("# Local Run Dashboard\n\n| Field | Value |\n|---|---|\n| Status | running |\n")

    _write_live_dice_dashboard(tmp_path, {
        "training.dice": {"value": 0.75, "step": 4},
        "validation.dice": {"value": 0.5, "step": 3},
        "validation.dice.lv": {"value": 0.6, "step": 3},
    })

    rendered = (tracking / "dashboard.md").read_text()
    assert "| train average | 0.7500 | 4 |" in rendered
    assert "| validation average | 0.5000 | 3 |" in rendered
    assert "| validation average / lv | 0.6000 | 3 |" in rendered


def test_live_dice_dashboard_replaces_generated_block(tmp_path):
    tracking = tmp_path / "tracking"
    tracking.mkdir()
    (tracking / "dashboard.md").write_text("# Local Run Dashboard\n")
    _write_live_dice_dashboard(tmp_path, {"training.dice": {"value": 0.1, "step": 1}})
    _write_live_dice_dashboard(tmp_path, {"training.dice": {"value": 0.2, "step": 2}})

    rendered = (tracking / "dashboard.md").read_text()
    assert rendered.count("<!-- live dice summary: begin -->") == 1
    assert "0.1000" not in rendered
    assert "| train average | 0.2000 | 2 |" in rendered
