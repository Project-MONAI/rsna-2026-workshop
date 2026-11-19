from tools.challenge_heartbeat import (
    DEFAULT_INTERVAL_SECONDS,
    MAX_INTERVAL_SECONDS,
    normalize_interval,
    replacement_job,
)


def test_replacement_job_preserves_each_completed_stage() -> None:
    cache_stage = {"state": "completed", "command": ["generate-cache"], "return_code": 0}
    preprocessing = replacement_job(cache_stage, {"state": "queued", "command": ["preprocess"]})
    assert preprocessing["execution_history"] == [cache_stage]

    preprocessing["state"] = "completed"
    training = replacement_job(preprocessing, {"state": "queued", "command": ["train"]})
    assert training["execution_history"] == [
        cache_stage,
        {"state": "completed", "command": ["preprocess"]},
    ]


def test_local_queue_interval_is_bounded_to_two_minutes() -> None:
    assert DEFAULT_INTERVAL_SECONDS == 120
    assert MAX_INTERVAL_SECONDS == 120
    assert normalize_interval(120) == 120
    assert normalize_interval(600) == 120
    try:
        normalize_interval(4)
    except RuntimeError as error:
        assert "at least 5 seconds" in str(error)
    else:
        raise AssertionError("intervals below five seconds must be rejected")


def test_heartbeat_runtime_dir_reads_private_env(tmp_path, monkeypatch) -> None:
    import tools.challenge_heartbeat as heartbeat

    monkeypatch.setattr(heartbeat, "ROOT", tmp_path)
    monkeypatch.delenv("MIAgent_RUNTIME_DIR", raising=False)
    expected = tmp_path.parent / "external-runtime"
    (tmp_path / ".env").write_text(f"MIAgent_RUNTIME_DIR={expected}\n")

    assert heartbeat.runtime_dir() == expected.resolve()
