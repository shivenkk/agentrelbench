"""
arb-run: run the EnterpriseOps-Gym benchmark k times per task, archiving a
post-seed and a final full-state export per run plus a batch manifest.

See docs/krun-wrapper-spec.md for the full behavioral contract. Usage:

    arb-run --tasks <dir> --llm-config <json> --k 8 --out runs/

HOW THIS ACTUALLY RUNS EOG (see README.md for the full rationale): this
process (running in agentrelbench's own, lightweight venv) never imports
EnterpriseOps-Gym itself. For each task it stages a one-task configs folder,
writes a small JSON job spec, and execs `agentrelbench.inner_runner` under
the *clone's own* venv Python (which already has langchain/ray/etc., plus
nest_asyncio) with PYTHONPATH extended to this package's `src/` -- so the
clone's venv can `import agentrelbench.eog_patch` without ever having
agentrelbench pip-installed into it. Only the clone's already-synced venv
runs EOG code; this process's own venv only needs httpx + stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from agentrelbench import collector
from agentrelbench.state_export import context_to_headers

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # src/agentrelbench/cli.py -> repo root
EOG_CLONE_ROOT = REPO_ROOT / "external" / "EnterpriseOps-Gym"
CLONE_VENV_PYTHON = EOG_CLONE_ROOT / ".venv" / "bin" / "python"


def _make_batch_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:6]}"


def _gym_headers_for_task(task_json: dict) -> Dict[str, Dict[str, str]]:
    gym_servers = task_json.get("gym_servers_config")
    if not gym_servers:
        raise ValueError(
            "task has no 'gym_servers_config' -- arb-run infers the domain/server "
            "from it and only supports the multi-gym task format (see "
            "docs/eog-technical-map.md §B)."
        )
    return {gym["mcp_server_url"]: context_to_headers(gym.get("context")) for gym in gym_servers}


def _run_one_task(
    task_file: Path,
    task_id: str,
    llm_config_path: Path,
    batch_dir: Path,
    k: int,
) -> None:
    task_json = json.loads(task_file.read_text())
    headers_by_gym_url = _gym_headers_for_task(task_json)

    task_output_dir = batch_dir / task_id
    task_output_dir.mkdir(parents=True, exist_ok=True)

    # Stage a one-file configs folder: EOG's --configs_folder globs *.json
    # unconditionally, and our storage layout needs one EOG invocation (and
    # therefore one clean run_N sequence) per task_id. The job spec file
    # must live OUTSIDE this directory -- it is itself JSON, and would
    # otherwise be picked up by that same glob as a second, invalid task.
    staging_dir = batch_dir / "_staging" / task_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(task_file, staging_dir / task_file.name)

    job_spec = {
        "configs_folder": str(staging_dir),
        "llm_config_path": str(llm_config_path),
        "output_folder": str(task_output_dir),
        "k": k,
        "concurrency": 1,
        "orchestrator": "react",
        "headers_by_gym_url": headers_by_gym_url,
        "clone_root": str(EOG_CLONE_ROOT),
    }
    job_spec_path = batch_dir / "_staging" / f"{task_id}.job_spec.json"
    job_spec_path.write_text(json.dumps(job_spec))

    env = os.environ.copy()
    src_dir = str(REPO_ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else src_dir

    result = subprocess.run(
        [str(CLONE_VENV_PYTHON), "-m", "agentrelbench.inner_runner", str(job_spec_path)],
        cwd=str(EOG_CLONE_ROOT),
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"EOG run failed for task {task_id!r} (exit code {result.returncode})")


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(prog="arb-run")
    parser.add_argument("--tasks", required=True, help="Directory of EOG task JSON files.")
    parser.add_argument("--llm-config", required=True, dest="llm_config", help="Path to an EOG llm_config JSON.")
    parser.add_argument("--k", required=True, type=int, help="Number of independent runs per task.")
    parser.add_argument("--out", required=True, help="Output root; the batch is created under here.")
    args = parser.parse_args(argv)

    tasks_dir = Path(args.tasks).resolve()
    llm_config_path = Path(args.llm_config).resolve()
    out_root = Path(args.out).resolve()

    if not CLONE_VENV_PYTHON.exists():
        print(f"ERROR: EOG clone venv python not found at {CLONE_VENV_PYTHON}", file=sys.stderr)
        return 1

    task_files = sorted(tasks_dir.glob("*.json"))
    if not task_files:
        print(f"ERROR: no task JSON files found in {tasks_dir}", file=sys.stderr)
        return 1

    batch_id = _make_batch_id()
    batch_dir = out_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    task_id_to_file = {task_file.stem: task_file for task_file in task_files}
    if len(task_id_to_file) != len(task_files):
        print("ERROR: task filenames must be unique once their .json suffix is stripped", file=sys.stderr)
        return 1

    started_at = collector.utc_now_iso()
    for task_id, task_file in task_id_to_file.items():
        try:
            _run_one_task(task_file, task_id, llm_config_path, batch_dir, args.k)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    finished_at = collector.utc_now_iso()

    try:
        collector.build_manifest(
            batch_dir=batch_dir,
            batch_id=batch_id,
            k=args.k,
            llm_config_path=llm_config_path,
            started_at=started_at,
            finished_at=finished_at,
            our_repo_root=REPO_ROOT,
            eog_clone_root=EOG_CLONE_ROOT,
            task_files=task_id_to_file,
        )
    except (collector.InvalidMissingDumpError, collector.PostSeedDriftError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Batch complete: {batch_dir}")
    return 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
