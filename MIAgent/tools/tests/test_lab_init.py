import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location("lab_init", Path(__file__).parents[2] / "containers/lab/init.py")
lab_init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab_init)


def test_recreation_resets_work_but_preserves_models(tmp_path, monkeypatch):
    monkeypatch.setattr(lab_init.os, "chown", lambda *args, **kwargs: None)
    seed, workspace, runtime, cache = [tmp_path / name for name in ("seed", "workspace", "runtime", "cache")]
    (seed / "skills/segmentation/example/bundle").mkdir(parents=True)
    (seed / "skills/segmentation/example/bundle/config.json").write_text("{}")
    (seed / "initial.txt").write_text("initial")
    marker = tmp_path / "container-layer/initialized"
    lab_init.initialize(seed, workspace, runtime, cache, marker)
    (workspace / "initial.txt").write_text("student change")
    (workspace / "inference_tmp/prediction.txt").write_text("output")
    (runtime / "logs/student.log").write_text("log")
    (workspace / "skills/segmentation/example/bundle/model.pt").write_text("weights")
    lab_init.initialize(seed, workspace, runtime, cache, marker)
    assert (workspace / "initial.txt").read_text() == "student change"
    marker.unlink()
    lab_init.initialize(seed, workspace, runtime, cache, marker)
    assert (workspace / "initial.txt").read_text() == "initial"
    assert not (workspace / "inference_tmp/prediction.txt").exists()
    assert not (runtime / "logs/student.log").exists()
    assert (workspace / "skills/segmentation/example/bundle/model.pt").read_text() == "weights"
