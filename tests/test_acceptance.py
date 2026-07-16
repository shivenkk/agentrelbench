"""
Acceptance test per docs/krun-wrapper-spec.md's "Acceptance test" section.

Fully offline (no LLM API keys): reuses m1_spike/'s scripted responder and
spike task to drive `arb-run --k 2` through the real EOG clone (still
requires the live csm container on :8001 -- seeding, tool calls, and
sql-runner dumps are real HTTP calls; only the *model* is a local stub, so
this isolates OUR wrapper's behavior from any LLM/API dependency, exactly as
m1_spike itself did).

Asserts, per spec:
  - run_1 and run_2 both have EOG results (results_*.json) and both state
    exports (post_seed_state.json.gz, final_state.json.gz).
  - post-seed exports are identical across runs (seeding is deterministic).
  - the manifest is complete.
  - corrupting (deleting) one run's final_state export makes the collector
    fail loudly with INVALID_MISSING_DUMP.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentrelbench import cli, collector

REPO_ROOT = Path(__file__).resolve().parent.parent
M1_SPIKE = REPO_ROOT / "m1_spike"
RESPONDER_SCRIPT = M1_SPIKE / "scripted_responder.py"
SCRIPT_JSON = M1_SPIKE / "script.json"
TASKS_DIR = M1_SPIKE / "tasks"
TASK_FILE = TASKS_DIR / "task.json"
LLM_CONFIG = M1_SPIKE / "llm_stub.json"  # hardcodes http://127.0.0.1:8099/v1
RESPONDER_PORT = 8099
RESPONDER_HOST = "127.0.0.1"


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


@pytest.fixture
def scripted_responder():
    """Starts m1_spike's offline mock LLM endpoint for the duration of the test."""
    proc = subprocess.Popen(
        [sys.executable, str(RESPONDER_SCRIPT), "--script", str(SCRIPT_JSON), "--port", str(RESPONDER_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for_port(RESPONDER_HOST, RESPONDER_PORT), "scripted responder did not come up on :8099"
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_k2_produces_complete_batch_then_detects_corruption(scripted_responder, tmp_path):
    out_dir = tmp_path / "runs"

    rc = cli.main(
        [
            "--tasks", str(TASKS_DIR),
            "--llm-config", str(LLM_CONFIG),
            "--k", "2",
            "--out", str(out_dir),
        ]
    )
    assert rc == 0, "arb-run should exit 0 on a clean k=2 run"

    batch_dirs = [p for p in out_dir.iterdir() if p.is_dir()]
    assert len(batch_dirs) == 1, f"expected exactly one batch dir, found {batch_dirs}"
    batch_dir = batch_dirs[0]

    task_dir = batch_dir / "task"  # task_id == filename stem of m1_spike/tasks/task.json
    run1, run2 = task_dir / "run_1", task_dir / "run_2"

    # --- both runs have EOG results + both state exports ---
    for run_dir in (run1, run2):
        results = list(run_dir.glob("results_*.json"))
        assert results, f"missing EOG results_*.json in {run_dir}"
        assert (run_dir / "post_seed_state.json.gz").exists(), f"missing post_seed_state in {run_dir}"
        assert (run_dir / "final_state.json.gz").exists(), f"missing final_state in {run_dir}"

        # EOG's own results should show the (deterministic, scripted) run passed.
        results_json = json.loads(results[0].read_text())
        run_result = results_json["runs"][0]
        assert run_result["overall_success"] is True, f"{run_dir} did not pass its verifiers: {run_result}"

    # --- post-seed exports identical across runs (free determinism monitor) ---
    dump1 = collector.read_gzip_json(run1 / "post_seed_state.json.gz")
    dump2 = collector.read_gzip_json(run2 / "post_seed_state.json.gz")
    assert dump1["tables"] == dump2["tables"], "post_seed_state should be identical across independently-seeded runs"
    assert dump1["database_id"] != dump2["database_id"], "each run must get its own fresh database_id"

    # --- manifest complete ---
    manifest_path = batch_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["k"] == 2
    assert manifest["agentrelbench_git_sha"], "expected our repo's git SHA to be recorded"
    assert manifest["eog_commit"], "expected the EOG clone's commit to be recorded"
    assert manifest["llm_config"]["llm_api_key"] == collector.REDACTED, "API key must be redacted"
    assert manifest["llm_config"]["max_tokens"] == 4096, "non-secret sampling fields must survive redaction"
    assert manifest["sampling_params"] == {"temperature": 0.0, "max_tokens": 4096}
    task_manifest = manifest["tasks"]["task"]
    assert task_manifest["task_file"] == str(TASK_FILE)
    assert len(task_manifest["runs"]) == 2
    for run_entry in task_manifest["runs"]:
        assert run_entry["status"] == "success"
        assert run_entry["database_id"]
        assert set(run_entry["artifacts"]) == {"results_json", "post_seed_state", "final_state"}

    # --- corrupt one final_state export; collector must fail loudly ---
    (run2 / "final_state.json.gz").unlink()
    with pytest.raises(collector.InvalidMissingDumpError, match="INVALID_MISSING_DUMP"):
        collector.build_manifest(
            batch_dir=batch_dir,
            batch_id=batch_dir.name,
            k=2,
            llm_config_path=LLM_CONFIG,
            started_at=manifest["started_at"],
            finished_at=manifest["finished_at"],
            our_repo_root=REPO_ROOT,
            eog_clone_root=REPO_ROOT / "external" / "EnterpriseOps-Gym",
            task_files={"task": TASK_FILE},
        )
