"""
Runs *inside* the EnterpriseOps-Gym clone's own venv, invoked as:

    <clone>/.venv/bin/python -m agentrelbench.inner_runner <job_spec.json>

with PYTHONPATH extended (by cli.py) to include this package's own `src/`
directory, so `agentrelbench` resolves via PYTHONPATH without ever being
pip-installed into the clone's venv (see README.md's "How arb-run runs EOG"
section for the full rationale).

This module is deliberately tiny: cli.py has already resolved which task,
what k, the output layout, and per-gym headers into a job spec; the only
thing left to do here is apply the agentrelbench.eog_patch and become
evaluate.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def main(argv: list = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m agentrelbench.inner_runner <job_spec.json>", file=sys.stderr)
        return 2

    job = json.loads(Path(argv[0]).read_text())

    clone_root = job["clone_root"]
    if clone_root not in sys.path:
        sys.path.insert(0, clone_root)

    from agentrelbench.eog_patch import apply_patch, set_run_context

    set_run_context(
        output_root=job["output_folder"],
        headers_by_gym_url=job["headers_by_gym_url"],
    )
    apply_patch()

    # Mirrors m1_spike's proven invocation convention (cd into the clone
    # before running evaluate.py); harmless for our own tasks' absolute
    # seed_database_file paths, and required for any task giving a
    # CWD-relative one (technical map §B).
    os.chdir(clone_root)

    import evaluate  # the clone's top-level evaluate.py, now import-patchable

    sys.argv = [
        "evaluate.py",
        "--configs_folder", job["configs_folder"],
        "--llm_config", job["llm_config_path"],
        "--output_folder", job["output_folder"],
        "--num_runs", str(job["k"]),
        "--concurrency", str(job.get("concurrency", 1)),
        "--orchestrator", job.get("orchestrator", "react"),
    ]
    asyncio.run(evaluate.main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
