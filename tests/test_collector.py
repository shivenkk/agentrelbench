"""Unit tests for agentrelbench.collector: manifest completeness, the
INVALID_MISSING_DUMP hard rule, post-seed drift detection, and API-key
redaction. Fabricates a batch directory on disk directly -- no live
containers, no EOG, no subprocesses.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentrelbench import collector
from agentrelbench.state_export import write_gzip_json

REPO_ROOT = Path(__file__).resolve().parent.parent
EOG_CLONE_ROOT = REPO_ROOT / "external" / "EnterpriseOps-Gym"


def _write_results(run_dir: Path, taskname: str, *, overall_success=True, error=None, total_tokens=42):
    payload = {
        "benchmark_config": {"model": "test/test"},
        "runs": [
            {
                "run_number": 1,
                "overall_success": overall_success,
                "error": error,
                "conversation_flow": [
                    {"type": "ai_message", "usage_metadata": {"total_tokens": total_tokens}},
                ],
            }
        ],
        "statistics": {},
    }
    (run_dir / f"results_{taskname}.json").write_text(json.dumps(payload))


def _write_dumps(run_dir: Path, database_id: str, tables: dict) -> None:
    dump = {"database_id": database_id, "tables": tables}
    write_gzip_json(dump, run_dir / "post_seed_state.json.gz")
    write_gzip_json(dump, run_dir / "final_state.json.gz")


def _make_batch(tmp_path: Path, *, n_runs: int = 2, drift: bool = False):
    batch_dir = tmp_path / "batch"
    task_dir = batch_dir / "taskA"
    base_tables = {"customer_case": [{"case_id": 1, "state": "new"}]}
    for i in range(1, n_runs + 1):
        run_dir = task_dir / f"run_{i}"
        run_dir.mkdir(parents=True)
        _write_results(run_dir, "taskA")
        run_tables = base_tables
        if drift and i == n_runs:
            run_tables = {"customer_case": [{"case_id": 1, "state": "DRIFTED"}]}
        _write_dumps(run_dir, database_id=f"db_{i}", tables=run_tables)

    task_file = tmp_path / "taskA.json"
    task_file.write_text(json.dumps({"user_prompt": "irrelevant, no gym_servers_config needed for this test"}))
    return batch_dir, task_file


def _llm_config(tmp_path: Path, **overrides) -> Path:
    cfg = {"llm_provider": "openrouter", "llm_model": "m", "llm_api_key": "sk-secret", "temperature": 0.0}
    cfg.update(overrides)
    path = tmp_path / "llm_config.json"
    path.write_text(json.dumps(cfg))
    return path


def _build(batch_dir, task_file, llm_config_path, k=2):
    return collector.build_manifest(
        batch_dir=batch_dir,
        batch_id="batch",
        k=k,
        llm_config_path=llm_config_path,
        started_at="t0",
        finished_at="t1",
        our_repo_root=REPO_ROOT,
        eog_clone_root=EOG_CLONE_ROOT,
        task_files={"taskA": task_file},
    )


def test_build_manifest_success(tmp_path):
    batch_dir, task_file = _make_batch(tmp_path)
    manifest = _build(batch_dir, task_file, _llm_config(tmp_path))

    assert manifest["k"] == 2
    assert set(manifest["tasks"].keys()) == {"taskA"}
    runs = manifest["tasks"]["taskA"]["runs"]
    assert len(runs) == 2
    assert manifest["llm_config"]["llm_api_key"] == collector.REDACTED
    assert manifest["sampling_params"] == {"temperature": 0.0}
    assert "task_file_sha256" in manifest["tasks"]["taskA"]
    for run in runs:
        assert run["status"] == "success"
        assert run["token_usage"] == 42
        assert run["database_id"].startswith("db_")
        assert set(run["artifacts"].keys()) == {"results_json", "post_seed_state", "final_state"}
    assert (batch_dir / "manifest.json").exists()


def test_build_manifest_missing_final_state_raises_invalid_missing_dump(tmp_path):
    batch_dir, task_file = _make_batch(tmp_path)
    (batch_dir / "taskA" / "run_2" / "final_state.json.gz").unlink()

    with pytest.raises(collector.InvalidMissingDumpError, match="INVALID_MISSING_DUMP"):
        _build(batch_dir, task_file, _llm_config(tmp_path))
    assert not (batch_dir / "manifest.json").exists()


def test_build_manifest_missing_post_seed_state_raises(tmp_path):
    batch_dir, task_file = _make_batch(tmp_path)
    (batch_dir / "taskA" / "run_1" / "post_seed_state.json.gz").unlink()

    with pytest.raises(collector.InvalidMissingDumpError, match="INVALID_MISSING_DUMP"):
        _build(batch_dir, task_file, _llm_config(tmp_path))


def test_build_manifest_missing_results_json_raises(tmp_path):
    batch_dir, task_file = _make_batch(tmp_path)
    (batch_dir / "taskA" / "run_1" / "results_taskA.json").unlink()

    with pytest.raises(collector.InvalidMissingDumpError, match="INVALID_MISSING_DUMP"):
        _build(batch_dir, task_file, _llm_config(tmp_path))


def test_build_manifest_post_seed_drift_raises(tmp_path):
    batch_dir, task_file = _make_batch(tmp_path, drift=True)

    with pytest.raises(collector.PostSeedDriftError):
        _build(batch_dir, task_file, _llm_config(tmp_path))


def test_build_manifest_single_run_has_no_drift_check(tmp_path):
    # A single-run batch has nothing to diff against -- must not raise.
    batch_dir, task_file = _make_batch(tmp_path, n_runs=1)
    manifest = _build(batch_dir, task_file, _llm_config(tmp_path), k=1)
    assert len(manifest["tasks"]["taskA"]["runs"]) == 1


def test_redact_llm_config_keeps_non_secret_fields():
    redacted = collector.redact_llm_config(
        {
            "llm_provider": "openrouter",
            "llm_model": "gpt",
            "llm_api_key": "sk-xyz",
            "llm_api_endpoint": "http://x",
            "temperature": 0.5,
        }
    )
    assert redacted["llm_api_key"] == collector.REDACTED
    assert redacted["llm_provider"] == "openrouter"
    assert redacted["llm_api_endpoint"] == "http://x"
    assert redacted["temperature"] == 0.5


def test_redact_llm_config_handles_missing_or_empty_key():
    redacted = collector.redact_llm_config({"llm_provider": "x", "llm_api_key": ""})
    assert redacted["llm_api_key"] == ""  # nothing to redact
    redacted = collector.redact_llm_config({"llm_provider": "x"})
    assert "llm_api_key" not in redacted


def test_redact_llm_config_does_not_false_positive_on_max_tokens():
    # Regression: a naive substring check ("token" in "max_tokens") would
    # wrongly redact this sampling param. "tokens" (plural) is not the whole
    # word "token", so it must survive untouched.
    redacted = collector.redact_llm_config({"llm_api_key": "sk-x", "max_tokens": 4096, "top_p": 0.9})
    assert redacted["max_tokens"] == 4096
    assert redacted["top_p"] == 0.9
    assert redacted["llm_api_key"] == collector.REDACTED


def test_sampling_params_extracts_known_keys_only():
    params = collector.sampling_params(
        {"llm_provider": "x", "temperature": 0.7, "max_tokens": 4096, "top_p": 0.9, "unrelated": "y"}
    )
    assert params == {"temperature": 0.7, "max_tokens": 4096, "top_p": 0.9}
