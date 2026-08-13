"""
arb-validate: task-validation CLI. Proves a task's oracle and counterexample
scripts produce their expected labeler verdicts end-to-end, through the real
k-run wrapper + damage labeler (no shortcuts): for oracle.script.json and
every counterexamples/*.script.json under a task directory, it

  1. extracts the file's ``"script"`` turn list to a temp JSON file (the
     bare-list format m1_spike/scripted_responder.py consumes),
  2. starts a fresh scripted_responder.py on a free localhost port,
  3. generates a one-off llm_config.json pointing at that port,
  4. invokes ``arb-run`` (in-process) with k=1 into a temp runs dir,
  5. runs the labeler over the resulting batch (agentrelbench.labeling),
  6. compares the produced verdict against the file's ``"expected"`` block
     (only the keys actually present there: outcome, sub_label, severity,
     dollars, eog_success),
  7. kills the responder,

then prints a result table and exits nonzero if any script's verdict
mismatched its expected block.

Usage:
    arb-validate --task tasks/csm/contract-price-correction

Requires the task domain's MCP container already running (e.g. csm on
:8001, per the task JSON's gym_servers_config) -- this CLI only stubs the
LLM, never the gym server.
"""
from __future__ import annotations

import argparse
import json
import math
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from agentrelbench import cli as arb_run_cli
from agentrelbench.labeling import DEFAULT_DATA_DIR, label_batch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # src/agentrelbench/validate.py -> repo root


def _responder_script() -> Path:
    """The scripted responder, in a checkout or an installed package.

    Same shape as labeling._default_data_dir: REPO_ROOT points into
    site-packages for a wheel, where m1_spike/ does not exist, so the responder
    ships beside the task suite.
    """
    packaged = Path(__file__).resolve().parent / "suite" / "scripted_responder.py"
    checkout = REPO_ROOT / "m1_spike" / "scripted_responder.py"
    return checkout if checkout.is_file() else packaged


RESPONDER_SCRIPT = _responder_script()
RESPONDER_HOST = "127.0.0.1"

# Only these keys are ever compared -- exactly the keys a task's *.script.json
# "expected" block may carry (tasks/csm/contract-price-correction/RATIONALE.md:
# "each counterexample must produce exactly its expected block (outcome,
# sub_label, severity, dollars)"; eog_success added per this CLI's spec).
EXPECTED_KEYS = ("outcome", "sub_label", "severity", "dollars", "eog_success")


# --------------------------------------------------------------- comparison


def _values_match(expected: Any, actual: Any) -> bool:
    """Numeric-tolerant equality: 8388 (int) and 8388.0 (float) are the same
    dollar figure regardless of which JSON numeric type either side used.
    Everything else (strings, bools, None) compares with plain ``==``."""
    if (
        isinstance(expected, int | float) and not isinstance(expected, bool)
        and isinstance(actual, int | float) and not isinstance(actual, bool)
    ):
        return math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-9)
    return expected == actual


def compare_verdict(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Compare only the keys present in ``expected`` against ``actual``
    (a verdicts.jsonl row). Returns human-readable mismatch descriptions;
    empty list means a full match."""
    mismatches = []
    for key in EXPECTED_KEYS:
        if key not in expected:
            continue
        if not _values_match(expected[key], actual.get(key)):
            mismatches.append(f"{key}: expected {expected[key]!r}, got {actual.get(key)!r}")
    return mismatches


# ------------------------------------------------------------------ script running


def _free_port() -> int:
    """Bind to port 0 to get an OS-assigned free localhost port, then
    release it immediately for the responder subprocess to bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((RESPONDER_HOST, 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _discover_scripts(task_dir: Path) -> list[tuple[str, Path]]:
    """[("oracle", oracle.script.json), (<name>, counterexamples/<name>.script.json), ...]."""
    scripts = [("oracle", task_dir / "oracle.script.json")]
    for path in sorted((task_dir / "counterexamples").glob("*.script.json")):
        scripts.append((path.name[: -len(".script.json")], path))
    return scripts


def _run_one_script(task_dir: Path, name: str, script_path: Path, data_dir: Path) -> dict[str, Any]:
    """Run a single *.script.json through arb-run (k=1) + the labeler, and
    compare the resulting verdict to the file's "expected" block. Returns a
    result dict: {name, expected, actual, mismatches, error}."""
    script_doc = json.loads(script_path.read_text())
    expected = script_doc["expected"]
    responder = None

    try:
        with tempfile.TemporaryDirectory(prefix=f"arb-validate-{name}-") as tmp:
            tmp_dir = Path(tmp)

            script_file = tmp_dir / "script.json"
            script_file.write_text(json.dumps(script_doc["script"]))

            port = _free_port()
            responder = subprocess.Popen(
                [sys.executable, str(RESPONDER_SCRIPT), "--script", str(script_file), "--port", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not _wait_for_port(RESPONDER_HOST, port):
                raise RuntimeError(f"scripted responder did not come up on :{port}")

            llm_config_path = tmp_dir / "llm_config.json"
            llm_config_path.write_text(json.dumps({
                "llm_provider": "openrouter",
                "llm_model": "scripted-responder",
                "llm_api_key": "not-needed",
                "llm_api_endpoint": f"http://{RESPONDER_HOST}:{port}/v1",
                "temperature": 0.0,
                "max_tokens": 4096,
            }))

            # Stage just task.json into its own flat tasks dir, named after
            # the real task directory so the batch's task_id (arb-run's
            # cli.py uses the filename stem) matches what _find_task_dir
            # expects when tasks_root == task_dir.parent.
            staged_tasks_dir = tmp_dir / "tasks"
            staged_tasks_dir.mkdir()
            (staged_tasks_dir / f"{task_dir.name}.json").write_text((task_dir / "task.json").read_text())

            runs_root = tmp_dir / "runs"
            rc = arb_run_cli.main([
                "--tasks", str(staged_tasks_dir),
                "--llm-config", str(llm_config_path),
                "--k", "1",
                "--out", str(runs_root),
            ])
            if rc != 0:
                raise RuntimeError(f"arb-run exited {rc} for script {name!r}")

            batch_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
            if len(batch_dirs) != 1:
                raise RuntimeError(f"expected exactly 1 batch dir under {runs_root}, found {batch_dirs}")
            batch_dir = batch_dirs[0]

            label_batch(batch_dir, tasks_root=task_dir.parent, data_dir=data_dir)

            verdict_lines = (batch_dir / "verdicts.jsonl").read_text().splitlines()
            if len(verdict_lines) != 1:
                raise RuntimeError(f"expected exactly 1 verdict for k=1, got {len(verdict_lines)}")
            actual = json.loads(verdict_lines[0])
    except Exception as exc:
        return {"name": name, "expected": expected, "actual": None, "mismatches": [], "error": str(exc)}
    finally:
        if responder is not None:
            responder.terminate()
            try:
                responder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                responder.kill()
                responder.wait(timeout=5)

    return {"name": name, "expected": expected, "actual": actual, "mismatches": compare_verdict(expected, actual), "error": None}


# ------------------------------------------------------------------------ CLI


def _print_table(results: list[dict[str, Any]]) -> None:
    name_width = max(len(r["name"]) for r in results) if results else 4
    header = f"{'script':<{name_width}}  {'result':<4}  details"
    print(header)
    print("-" * len(header))
    for r in results:
        if r["error"]:
            print(f"{r['name']:<{name_width}}  {'FAIL':<4}  error: {r['error']}")
            continue
        ok = not r["mismatches"]
        detail = "expected " + json.dumps(r["expected"], sort_keys=True) if ok else "; ".join(r["mismatches"])
        print(f"{r['name']:<{name_width}}  {'OK' if ok else 'FAIL':<4}  {detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arb-validate")
    parser.add_argument("--task", required=True, help="Task directory (e.g. tasks/csm/contract-price-correction).")
    parser.add_argument(
        "--data", default=str(DEFAULT_DATA_DIR), dest="data_dir",
        help="Directory with per-domain primary-keys-*.json / volatile-columns-*.json (default: data/eog).",
    )
    args = parser.parse_args(argv)

    task_dir = Path(args.task).resolve()
    data_dir = Path(args.data_dir)
    scripts = _discover_scripts(task_dir)
    if not scripts:
        print(f"ERROR: no oracle.script.json/counterexamples found under {task_dir}", file=sys.stderr)
        return 1

    results = [_run_one_script(task_dir, name, path, data_dir) for name, path in scripts]

    _print_table(results)

    failed = any(r["error"] or r["mismatches"] for r in results)
    return 1 if failed else 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
