"""
Labeling glue: turns k-run wrapper output (docs/krun-wrapper-spec.md;
runs/<batch_id>/<task_id>/run_N/{results_*.json, post_seed_state.json.gz,
final_state.json.gz}) into agentrelbench.labeler verdicts for a whole batch.

Three pieces:
  - load_states:    per-run state export loading (-> label_run's
                    initial_state/final_state + a dumps_present flag).
  - build_run_meta: per-run RunMeta from one run's parsed results_*.json
                    (termination / final_message / eog_success -- see its
                    docstring for the exact field mapping, verified against
                    m1_spike/results/run_1/results_task.json and EOG's own
                    benchmark/executor.py + orchestrators/react.py).
  - label_batch:    walks a whole batch, resolves each task's DamageSpec +
                    per-domain canonicalization data, and writes
                    verdicts.jsonl + summary.json into the batch dir.

Also exposes the `arb-label` CLI (see main()/entrypoint()).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentrelbench import collector
from agentrelbench.labeler import (
    DamageSpec,
    InvalidRunError,
    RunMeta,
    RunVerdict,
    label_run,
    summarize,
)
from agentrelbench.state_export import read_gzip_json

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # src/agentrelbench/labeling.py -> repo root
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "eog"


# --------------------------------------------------------------- state export


def load_states(run_dir: Path) -> tuple[dict[str, list[dict]], dict[str, list[dict]], bool]:
    """Load one run's pre/post-mutation table states from its k-run wrapper
    exports (docs/krun-wrapper-spec.md: post_seed_state.json.gz written
    immediately after seeding, final_state.json.gz written immediately
    before EOG's cleanup deletes the DB).

    Returns ``(initial_state, final_state, dumps_present)``:
      - ``initial_state`` / ``final_state``: the ``"tables"`` dict of each
        gzip-JSON export (``{table: [row_dict, ...]}``, matching
        ``label_run``'s expected state shape) -- NOT the raw dump, which is
        also wrapped with a ``"database_id"`` key.
      - ``dumps_present``: False if EITHER export is missing from
        ``run_dir``. damage-labeler-spec.md sec2's hard assertion is about
        the pre-cleanup (final) dump specifically, but a missing post-seed
        dump leaves no valid ``initial_state`` to diff from either, so it is
        treated the same way here: both exports are required, or the run is
        not labeled (see ``label_batch``, which turns this into a
        ``RunMeta(dumps_present=False)`` so ``label_run`` raises
        ``InvalidRunError`` rather than silently diffing against ``{}``).

    When ``dumps_present`` is False, both state dicts are returned as ``{}``
    -- harmless, since ``label_run`` checks ``run_meta.dumps_present`` before
    ever touching either state.
    """
    post_seed_path = run_dir / "post_seed_state.json.gz"
    final_path = run_dir / "final_state.json.gz"
    dumps_present = post_seed_path.exists() and final_path.exists()
    if not dumps_present:
        return {}, {}, False
    initial_state = read_gzip_json(post_seed_path)["tables"]
    final_state = read_gzip_json(final_path)["tables"]
    return initial_state, final_state, True


# ----------------------------------------------------------------- run meta


def _eog_success(run: dict[str, Any]) -> bool:
    """True iff every verifier in ``run["verification_results"]`` passed.

    Field ground truth: m1_spike/results/run_1/results_task.json ->
    runs[0].verification_results.<name> == {"passed": true, "expected":..,
    "actual":.., "comparison_type":.., "query":.., "details":..}. This is
    computed independently from the verifier-level ``passed`` fields (not
    just trusting the precomputed ``run["overall_success"]``), though EOG's
    own benchmark/executor.py:371 computes ``overall_success`` the exact
    same way (``all(v["passed"] for v in verification_results.values())``).

    A run with no ``verification_results`` at all -- e.g. an errored run,
    whose dict is only ``{"run_number":.., "error": str(e),
    "overall_success": False}`` per benchmark/executor.py's
    execute_benchmark() except-branch, and which never reaches verification
    -- is conservatively False, not vacuously True.
    """
    verification_results = run.get("verification_results")
    if not verification_results:
        return False
    return all(v.get("passed") is True for v in verification_results.values())


def _final_message(run: dict[str, Any]) -> str | None:
    """The last assistant message in the conversation flow: the ``content``
    of the LAST entry of ``run["conversation_flow"]`` whose ``"type"`` is
    ``"ai_message"`` (scanning from the end). Used only as input to the
    labeler's sec5b ``REFUSAL:`` regex scan.

    None if there is no such entry (e.g. an errored run has no
    conversation_flow key at all). Note this is not always the same as the
    top-level ``run["model_response"]`` field: model_response is
    ``messages[-1].content`` (orchestrators/react.py), which on a stalled
    run (step budget exhausted mid-tool-call-loop) would be a tool result's
    JSON dump rather than any assistant content -- scanning conversation_flow
    for the true last *assistant* turn is what the spec's "final assistant
    message" wording asks for.
    """
    for message in reversed(run.get("conversation_flow") or []):
        if message.get("type") == "ai_message":
            return message.get("content")
    return None


def _stalled(run: dict[str, Any]) -> bool:
    """True iff the ReAct loop (external/EnterpriseOps-Gym/orchestrators/
    react.py) exhausted its step budget without producing a final, tool-free
    answer.

    The loop's only voluntary exit is: append an "ai_message" to
    conversation_flow, see its tool_calls list is empty, and break -- so a
    normal completion's LAST conversation_flow entry is always an
    "ai_message". Exhausting ``max_iterations`` (orchestrators/base.py,
    default 50) instead stops the loop right after executing the final
    round of tool calls, so the flow ends on a "tool_result" entry, with no
    final answer ever produced. An empty/missing conversation_flow (no
    entries at all) is treated the same way: no final answer was ever
    recorded.
    """
    flow = run.get("conversation_flow") or []
    if not flow:
        return True
    return flow[-1].get("type") != "ai_message"


def _termination(run: dict[str, Any]) -> str:
    """"errored" | "stalled" | "completed" -- see build_run_meta's docstring
    for the full field mapping this composes."""
    if run.get("error"):
        return "errored"
    if _stalled(run):
        return "stalled"
    return "completed"


def build_run_meta(results_json: dict[str, Any]) -> RunMeta:
    """Build a :class:`agentrelbench.labeler.RunMeta` from one run's fully
    parsed ``results_*.json`` (the whole file's top-level dict --
    ``{"benchmark_config":.., "runs": [...], "statistics": {...}}``; each
    run_N directory's results file has exactly one element in ``"runs"``,
    mirroring collector.py's own ``(results.get("runs") or [{}])[0]``
    indexing -- EOG's ``--num_runs k`` produces k separate run_N output
    folders, not k entries in one file).

    ``dumps_present`` is always left at its dataclass default (True): a
    results file alone can't tell you whether the state exports exist --
    callers (``label_batch``) combine this with ``load_states``'s own
    ``dumps_present`` before calling ``label_run``.

    Field mapping (verified against
    m1_spike/results/run_1/results_task.json, and against EOG's own source
    -- benchmark/executor.py's execute_single_run/execute_benchmark and
    orchestrators/react.py -- for the shape of both a normal AND an
    exception-wrapped run dict):

    - ``eog_success``:    see :func:`_eog_success`
        (``run["verification_results"][name]["passed"]``, all True).
    - ``final_message``:  see :func:`_final_message`
        (last ``run["conversation_flow"]`` entry with ``type ==
        "ai_message"``, its ``"content"``).
    - ``termination``:    see :func:`_termination` / :func:`_stalled`.
        * "errored"   -- ``run["error"]`` is truthy. Set only by
          benchmark/executor.py's execute_benchmark() except-branch (an
          uncaught agent/tool exception): ``{"run_number":.., "error":
          str(e), "overall_success": False}``, with no ``conversation_flow``
          key at all.
        * "stalled"   -- not errored, and the ReAct loop's step budget
          (``max_iterations``, default 50) was exhausted without a final,
          tool-free answer (see :func:`_stalled`).
        * "completed" -- otherwise (the LLM voluntarily produced a final
          answer with no pending tool calls).
    """
    runs = results_json.get("runs")
    if not runs:
        # Silent-discard audit item #3: an empty/absent runs array would fall
        # through to a default dict and mislabel the run as stalled_clean.
        raise InvalidRunError(
            code="INVALID_EMPTY_RESULTS",
            message="results file has an empty/absent 'runs' array; refusing to label",
        )
    run = runs[0]
    return RunMeta(
        termination=_termination(run),
        final_message=_final_message(run),
        eog_success=_eog_success(run),
    )


# --------------------------------------------------------- task/domain data


def _find_task_dir(tasks_root: Path, task_id: str) -> Path:
    """Locate the task directory (containing damage.json) for a batch's
    ``task_id`` (the run-directory name arb-run assigned, i.e. the task
    JSON's filename stem -- see cli.py's ``task_id_to_file``).

    Tries ``tasks_root / task_id`` directly first (the common case: a
    single task's own parent directory, e.g. what arb-validate passes), then
    falls back to searching under ``tasks_root`` for a directory named
    exactly ``task_id`` that contains a damage.json (the multi-domain case,
    e.g. ``tasks_root`` == the repo's whole ``tasks/`` root, with an
    intervening ``<domain>/`` level).
    """
    direct = tasks_root / task_id
    if (direct / "damage.json").exists():
        return direct
    for damage_path in sorted(tasks_root.rglob("damage.json")):
        if damage_path.parent.name == task_id:
            return damage_path.parent
    raise FileNotFoundError(f"no damage.json found for task_id {task_id!r} under {tasks_root}")


def _load_primary_keys(data_dir: Path, domain: str) -> dict[str, str]:
    """data/eog/primary-keys-<domain>.json -> {table: pk_column}."""
    raw = json.loads((data_dir / f"primary-keys-{domain}.json").read_text())
    return raw["primary_keys"]


def _load_volatile_columns(data_dir: Path, domain: str) -> dict[str, list[str]]:
    """data/eog/volatile-columns-<domain>.json -> {table: [column, ...]}.

    The on-disk file is an M1-audit evidence dump keyed by ``"<table>.
    <column>"`` (each entry itself also carrying ``"table"``/``"column"``
    fields) rather than the ``{table: [columns]}`` shape label_run expects
    directly, so this reshapes it.
    """
    raw = json.loads((data_dir / f"volatile-columns-{domain}.json").read_text())
    by_table: dict[str, list[str]] = {}
    for entry in raw.get("volatile_columns", {}).values():
        by_table.setdefault(entry["table"], []).append(entry["column"])
    return by_table


def _load_task_damage_spec(
    tasks_root: Path, data_dir: Path, task_id: str
) -> tuple[DamageSpec, dict[str, list[str]], dict[str, str]]:
    """Resolve one task_id's (DamageSpec, volatile_columns, primary_keys)."""
    task_dir = _find_task_dir(tasks_root, task_id)
    damage_json = json.loads((task_dir / "damage.json").read_text())
    domain = damage_json["domain"]
    damage_spec = DamageSpec.from_task(
        damage_json.get("allowed", []),
        damage_json.get("pricing", []),
        damage_json.get("params", {}),
    )
    primary_keys = _load_primary_keys(data_dir, domain)
    volatile_columns = _load_volatile_columns(data_dir, domain)
    return damage_spec, volatile_columns, primary_keys


# ------------------------------------------------------------------ output


def _verdict_row(task_id: str, run_name: str, verdict: RunVerdict) -> dict[str, Any]:
    """Flatten one RunVerdict into a JSON-able dict for verdicts.jsonl.
    Field names match the task-script "expected" block convention
    (tasks/csm/contract-price-correction/*.script.json): outcome, sub_label,
    severity, dollars, eog_success."""
    return {
        "task_id": task_id,
        "run": run_name,
        "outcome": verdict.outcome,
        "sub_label": verdict.sub_label,
        "eog_success": verdict.success,
        "severity": verdict.damage.severity,
        "dollars": verdict.damage.dollars,
        "counts_as_damage": verdict.counts_as_damage,
        "counts_as_damage_upper": verdict.counts_as_damage_upper,
        "refusal_declared": verdict.refusal_declared,
        "inconsistency_flags": verdict.inconsistency_flags,
        "deltas": [
            {
                "table": d.table,
                "op": d.op,
                "key": d.key,
                "changed_columns": d.changed_columns,
                "severity": d.severity,
                "dollars": d.dollars,
            }
            for d in verdict.damage.deltas
        ],
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


_SQLITE_INTERNAL_PREFIX = "sqlite_"


def _scope_to_known_tables(state: dict[str, list[dict]], primary_keys: dict[str, str]) -> dict[str, list[dict]]:
    """Restrict a dumped state to the domain's primary-keys registry
    (data/eog/primary-keys-<domain>.json), loudly.

    SQLite's own bookkeeping tables (reserved ``sqlite_`` prefix, e.g.
    ``sqlite_sequence``) are excluded silently: they aren't domain schema, and
    their changes are pure derivatives of real-table inserts the diff already
    sees. ANY other table missing from the registry raises, a table the diff
    can't see is a blind spot in the damage axis (e.g. a new table appearing in
    an updated MCP image), and the measurement core never skips silently.
    """
    scoped: dict[str, list[dict]] = {}
    unknown: list[str] = []
    for table, rows in state.items():
        if table.startswith(_SQLITE_INTERNAL_PREFIX):
            continue
        if table not in primary_keys:
            unknown.append(table)
            continue
        scoped[table] = rows
    if unknown:
        raise ValueError(
            f"tables {sorted(unknown)} present in the state dump but missing from the "
            f"primary-keys registry; refusing to diff with a blind spot, add them to "
            f"data/eog/primary-keys-<domain>.json"
        )
    return scoped


def label_batch(batch_dir: Path, tasks_root: Path, data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
    """Label every run of a completed k-run batch
    (runs/<batch_id>/<task_id>/run_N/, docs/krun-wrapper-spec.md), writing:

      - ``<batch_dir>/verdicts.jsonl`` -- one JSON object per run (see
        :func:`_verdict_row`).
      - ``<batch_dir>/summary.json``   -- ``labeler.summarize()`` over every
        verdict in the batch, plus a ``"by_task"`` breakdown (the same
        summary fields, scoped per task_id).

    Each task's DamageSpec is located from its ``damage.json`` under
    ``tasks_root`` (see :func:`_find_task_dir`); ``damage.json``'s own
    ``"domain"`` field selects that domain's
    ``data/eog/{primary-keys,volatile-columns}-<domain>.json``.

    Propagates :class:`agentrelbench.labeler.InvalidRunError`
    (``INVALID_MISSING_DUMP``) from the first run missing a state dump --
    per spec, this must fail the whole batch loudly rather than skip the
    run (see :func:`load_states`).

    Returns the summary dict (the same content written to summary.json).
    """
    batch_dir = Path(batch_dir)
    tasks_root = Path(tasks_root)
    data_dir = Path(data_dir)

    tasks = collector.discover_batch(batch_dir)

    verdict_rows: list[dict[str, Any]] = []
    verdicts_by_task: dict[str, list[RunVerdict]] = {}

    for task_id, run_dirs in tasks.items():
        damage_spec, volatile_columns, primary_keys = _load_task_damage_spec(tasks_root, data_dir, task_id)

        task_verdicts: list[RunVerdict] = []
        for run_dir in run_dirs:
            results_files = sorted(run_dir.glob("results_*.json"))
            initial_state, final_state, dumps_present = load_states(run_dir)
            initial_state = _scope_to_known_tables(initial_state, primary_keys)
            final_state = _scope_to_known_tables(final_state, primary_keys)

            if results_files:
                results_json = json.loads(results_files[0].read_text())
                run_meta = build_run_meta(results_json)
            else:
                run_meta = RunMeta()
            # Both a results file AND both state dumps are required to ever
            # emit a verdict (see load_states + label_run's own hard check).
            run_meta.dumps_present = dumps_present and bool(results_files)

            verdict = label_run(
                initial_state=initial_state,
                final_state=final_state,
                damage_spec=damage_spec,
                volatile_columns=volatile_columns,
                primary_keys=primary_keys,
                run_meta=run_meta,
            )
            task_verdicts.append(verdict)
            verdict_rows.append(_verdict_row(task_id, run_dir.name, verdict))

        verdicts_by_task[task_id] = task_verdicts

    all_verdicts = [v for verdicts in verdicts_by_task.values() for v in verdicts]
    summary = {
        **summarize(all_verdicts),
        "by_task": {task_id: summarize(verdicts) for task_id, verdicts in verdicts_by_task.items()},
    }

    _write_jsonl(batch_dir / "verdicts.jsonl", verdict_rows)
    (batch_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary


# ------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arb-label")
    parser.add_argument("batch_dir", help="Batch directory produced by arb-run (runs/<batch_id>).")
    parser.add_argument(
        "--tasks", required=True, dest="tasks_root",
        help="Root directory containing task folders (task.json + damage.json each).",
    )
    parser.add_argument(
        "--data", default=str(DEFAULT_DATA_DIR), dest="data_dir",
        help="Directory with per-domain primary-keys-*.json / volatile-columns-*.json (default: data/eog).",
    )
    args = parser.parse_args(argv)

    try:
        summary = label_batch(Path(args.batch_dir), Path(args.tasks_root), Path(args.data_dir))
    except InvalidRunError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
