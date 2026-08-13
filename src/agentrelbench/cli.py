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
nest_asyncio) with PYTHONPATH extended to the directory this package sits
in -- so the clone's venv can `import agentrelbench.eog_patch` without ever
having agentrelbench pip-installed into it. Only the clone's already-synced
venv runs EOG code; this process's own venv only needs httpx + stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from agentrelbench import collector
from agentrelbench.state_export import context_to_headers

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # src/agentrelbench/cli.py -> repo root


def _eog_clone_root() -> Path:
    """Locate the EOG clone, in a checkout or from an installed package.

    Same problem as labeling._default_data_dir, without the same escape: the
    clone is a separate repository with its own uv-synced venv, whose python
    this process execs, so it can never ship inside our wheel. In a checkout it
    sits at <repo>/external/EnterpriseOps-Gym; from an install REPO_ROOT points
    into site-packages, where nothing was ever cloned, so ARB_EOG_CLONE is the
    only way to name it -- and one env var covers arb-validate too, which drives
    arb-run in-process and so cannot pass it a flag.

    Resolved to an absolute path because inner_runner chdirs into the clone and
    puts it on sys.path, after which a relative path names something else.
    """
    override = os.environ.get("ARB_EOG_CLONE")
    if override:
        return Path(override).resolve()
    return REPO_ROOT / "external" / "EnterpriseOps-Gym"


def _clone_venv_python(clone_root: Path) -> Path:
    return clone_root / ".venv" / "bin" / "python"


def _make_batch_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:6]}"


def find_repo_root(start: Path) -> Path:
    """Nearest ancestor of ``start`` that anchors relative seed paths.

    Anchoring on the task file rather than on this module is what makes seed
    resolution work when agentrelbench is pip-installed: ``REPO_ROOT`` is derived
    from ``__file__``, so for an installed package it points into site-packages,
    where no seed database has ever lived.

    Two anchors, because there are two valid layouts. In a checkout the anchor is
    ``pyproject.toml`` at the repo root. In an installed wheel the suite ships
    under ``agentrelbench/suite/``, which has no pyproject.toml above it, so the
    anchor is the presence of ``data/seed-dbs``. In a checkout both sit at the
    repo root and agree.
    """
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
        if (candidate / "data" / "seed-dbs").is_dir():
            return candidate
    return REPO_ROOT


def resolve_seed_paths(task_json: dict, task_file: Path | None = None) -> dict:
    """Return a copy of ``task_json`` with every seed_database_file absolute.

    Committed task.json files carry repo-relative seed paths so the suite is
    portable. They cannot stay relative by the time EOG reads them: inner_runner
    does ``os.chdir(clone_root)`` first, so a relative path would resolve against
    the EOG clone instead of this repo. Resolving here, before that chdir, makes
    the chdir irrelevant and asks nothing of whoever clones the repo.

    Relative paths resolve against the repo containing ``task_file`` when given,
    which keeps working for an installed package. Absolute paths pass through
    unchanged. A path that does not exist raises: a mis-seeded run is worse than
    a crashed one, because it still produces data.
    """
    anchor = find_repo_root(Path(task_file).resolve().parent) if task_file else REPO_ROOT
    resolved = json.loads(json.dumps(task_json))  # deep copy, JSON in / JSON out
    for gym in resolved.get("gym_servers_config") or []:
        seed = gym.get("seed_database_file")
        if seed is None:
            continue
        path = Path(seed)
        if not path.is_absolute():
            path = anchor / path
        if not path.exists():
            raise FileNotFoundError(
                f"seed_database_file does not exist: {path} (from {seed!r}). "
                f"Relative paths resolve against {anchor}."
            )
        gym["seed_database_file"] = str(path)
    return resolved


def _gym_headers_for_task(task_json: dict) -> dict[str, dict[str, str]]:
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
    clone_root: Path,
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
    # Not a plain copy: seed paths are resolved to absolute here, before
    # inner_runner chdirs into the clone (see resolve_seed_paths). The staged
    # file is also the record of what actually ran.
    (staging_dir / task_file.name).write_text(
        json.dumps(resolve_seed_paths(task_json, task_file), indent=2)
    )

    job_spec = {
        "configs_folder": str(staging_dir),
        "llm_config_path": str(llm_config_path),
        "output_folder": str(task_output_dir),
        "k": k,
        "concurrency": 1,
        "orchestrator": "react",
        "headers_by_gym_url": headers_by_gym_url,
        "clone_root": str(clone_root),
    }
    job_spec_path = batch_dir / "_staging" / f"{task_id}.job_spec.json"
    job_spec_path.write_text(json.dumps(job_spec))

    env = os.environ.copy()
    # The directory our package sits in -- <repo>/src in a checkout, site-packages
    # from an install -- which is what the clone's venv imports agentrelbench from.
    # Deriving it from REPO_ROOT would name a src/ that only a checkout has.
    package_parent = str(Path(__file__).resolve().parent.parent)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{package_parent}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else package_parent

    result = subprocess.run(
        [str(_clone_venv_python(clone_root)), "-m", "agentrelbench.inner_runner", str(job_spec_path)],
        cwd=str(clone_root),
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"EOG run failed for task {task_id!r} (exit code {result.returncode})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arb-run")
    parser.add_argument("--tasks", required=True, help="Directory of EOG task JSON files.")
    parser.add_argument("--llm-config", required=True, dest="llm_config", help="Path to an EOG llm_config JSON.")
    parser.add_argument("--k", required=True, type=int, help="Number of independent runs per task.")
    parser.add_argument("--out", required=True, help="Output root; the batch is created under here.")
    args = parser.parse_args(argv)

    tasks_dir = Path(args.tasks).resolve()
    llm_config_path = Path(args.llm_config).resolve()
    out_root = Path(args.out).resolve()

    # Resolved once per batch, not once per task: the manifest records this clone
    # as the substrate for every run in the batch, so it must not be re-read from
    # the environment midway through one.
    clone_root = _eog_clone_root()
    venv_python = _clone_venv_python(clone_root)
    if not venv_python.exists():
        print(
            f"ERROR: EOG clone venv python not found at {venv_python}\n"
            "arb-run only ever runs EOG under the clone's own venv, and the clone is a "
            "separate repository that is not shipped with this package. Clone it, sync it, "
            "and point ARB_EOG_CLONE at it:\n"
            "  git clone https://github.com/ServiceNow/EnterpriseOps-Gym\n"
            "  cd EnterpriseOps-Gym && uv sync --extra openai\n"
            "  export ARB_EOG_CLONE=$PWD",
            file=sys.stderr,
        )
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
            _run_one_task(task_file, task_id, llm_config_path, batch_dir, args.k, clone_root)
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
            eog_clone_root=clone_root,
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
