"""
Import-time patch for EnterpriseOps-Gym's per-run database lifecycle.

PATCH POINT (verified against the pinned clone, commit
de22905d21a080b83bf4a54258afe4250ee2dd55):

  benchmark/executor.py:11 does
      from benchmark.mcp_client import MCPClient, create_database_from_file, delete_database
  binding `create_database_from_file` and `delete_database` as bare names in
  benchmark.executor's own module namespace. Both names are referenced as
  bare globals:
    - the seed call-site, BenchmarkExecutor.execute_single_run
      (benchmark/executor.py:323): db_id = create_database_from_file(...)
    - the delete call-site, BenchmarkExecutor.execute_benchmark's `finally`
      cleanup block (benchmark/executor.py:553-563):
          for db_info in self.auto_created_databases:
              delete_database(db_info["gym_url"], db_info["database_id"])

  Python resolves a bare-name global from the *enclosing module's* __dict__
  at call time, not at def time. So replacing
  `benchmark.executor.create_database_from_file` and
  `benchmark.executor.delete_database` -- any time after both modules are
  imported, but before BenchmarkExecutor.execute_benchmark() actually runs --
  transparently redirects both call sites without editing a single tracked
  file in the clone.

WHAT WE WRAP
  - create_database_from_file(gym_url, sql_file_path) -> db_id:
        call straight through to the original, then (if a db_id came back)
        dump full state via /api/sql-runner into
        <run_dir>/post_seed_state.json.gz.
  - delete_database(gym_url, database_id) -> bool:
        dump full state into <run_dir>/final_state.json.gz, then call
        straight through to the original delete (always -- see
        wrapped_delete_database's docstring for why cleanup is protected
        even when our own dump raises).

RUN-DIRECTORY CORRELATION (documented limitation)
  Neither wrapped function receives an explicit "which output run_N is this"
  parameter, so correlation is done with a 1-based counter that increments
  once per create_database_from_file call and is expected to line up with
  EOG's own `run_{idx+1}` folder naming (evaluate.py:318). That assumption
  holds under the contract cli.py always sets up: exactly one task JSON fed
  to a given process (see cli.py's per-task staging), --concurrency forced
  to 1, and the task's own (inner) `number_of_runs` left at 1 (true of every
  shipped task and the m1_spike task). It would NOT hold across EOG's
  whole-sample retry path (evaluate.py's execute_sample, max_num_attempts=5,
  which re-seeds within the *same* outer run on error) -- a retry would
  advance our counter without EOG advancing its own run_N. This is a known,
  accepted gap: the offline acceptance path (scripted responder) is fully
  deterministic and triggers zero retries (confirmed in m1_spike's
  SPIKE-RESULT.md), and real-LLM retries only fire on infra-level
  exceptions, not on verifier failures. Not defended against here to avoid
  the complexity/fragility of stack-frame introspection for a rare path the
  acceptance test does not exercise.
"""
from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentrelbench.state_export import dump_all_tables, write_gzip_json

logger = logging.getLogger(__name__)


class EOGPatchError(RuntimeError):
    """Raised when the EOG clone's code no longer matches the shape this
    patch expects (symbol missing/renamed, signature drift, or the
    create/delete correlation assumption was violated). Deliberately loud --
    silently skipping would defeat the point of the state-export guarantee."""


_STATE: dict[str, Any] = {
    "output_root": None,  # Path: this task's output folder; EOG creates run_N under it
    "headers_by_gym_url": {},  # {mcp_server_url: {header_name: header_value}}
    "run_counter": 0,  # increments once per create_database_from_file call
    "pending_final": {},  # database_id -> run_dir (Path), consumed at delete time
    "patched": False,
}


def set_run_context(output_root: Any, headers_by_gym_url: dict[str, dict[str, str]] | None) -> None:
    """Register the per-task context the patched functions need. Call once,
    before invoking evaluate.main(), for each task's EOG subprocess."""
    _STATE["output_root"] = Path(output_root)
    _STATE["headers_by_gym_url"] = dict(headers_by_gym_url or {})
    _STATE["run_counter"] = 0
    _STATE["pending_final"] = {}


def _headers_for(gym_url: str) -> dict[str, str]:
    return dict(_STATE["headers_by_gym_url"].get(gym_url, {}))


def _check_symbol(module: Any, name: str, expected_params: tuple[str, ...]) -> Callable:
    """Defensive existence + shape check. Raises EOGPatchError (loudly, not
    silently) if the clone's code drifted from what this patch assumes."""
    if not hasattr(module, name):
        raise EOGPatchError(
            f"EOG code drift: {module.__name__}.{name} no longer exists; "
            f"cannot apply the database-lifecycle patch."
        )
    fn = getattr(module, name)
    if not callable(fn):
        raise EOGPatchError(f"EOG code drift: {module.__name__}.{name} is not callable.")
    params = tuple(inspect.signature(fn).parameters.keys())
    if params != expected_params:
        raise EOGPatchError(
            f"EOG code drift: {module.__name__}.{name} signature changed: "
            f"expected params {expected_params}, found {params}."
        )
    return fn


def apply_patch() -> None:
    """Apply the create/delete monkeypatch. Idempotent; safe to call more
    than once (subsequent calls are no-ops)."""
    if _STATE["patched"]:
        return

    import benchmark.executor as executor_mod
    import benchmark.mcp_client as mcp_client_mod

    orig_create = _check_symbol(executor_mod, "create_database_from_file", ("gym_url", "sql_file_path"))
    orig_delete = _check_symbol(executor_mod, "delete_database", ("gym_url", "database_id"))

    # Confirm executor.py's `from benchmark.mcp_client import ...` is still a
    # direct, unwrapped re-export. If executor.py started wrapping/aliasing
    # these names, patching benchmark.executor's copy would silently miss
    # the real call site -- fail loudly instead of assuming.
    if orig_create is not getattr(mcp_client_mod, "create_database_from_file", None):
        raise EOGPatchError(
            "EOG code drift: benchmark.executor.create_database_from_file is no "
            "longer the same object as benchmark.mcp_client.create_database_from_file."
        )
    if orig_delete is not getattr(mcp_client_mod, "delete_database", None):
        raise EOGPatchError(
            "EOG code drift: benchmark.executor.delete_database is no longer the "
            "same object as benchmark.mcp_client.delete_database."
        )

    # Silent-discard audit item #4 (docs/silent-discard-audit.md):
    # MCPClient.list_tools swallows discovery failures to [] -- the agent then
    # runs tool-less and the run records as a clean stall. Empty discovery is
    # an infrastructure failure, never data: fail loudly instead.
    orig_list_tools = mcp_client_mod.MCPClient.list_tools

    async def guarded_list_tools(self, *args, **kwargs):
        tools = await orig_list_tools(self, *args, **kwargs)
        if not tools:
            raise EOGPatchError(
                "MCP tool discovery returned an empty tool list -- server/session "
                "failure; refusing to run the agent tool-less (audit item #4)."
            )
        return tools

    mcp_client_mod.MCPClient.list_tools = guarded_list_tools

    def wrapped_create_database_from_file(gym_url: str, sql_file_path: str) -> str | None:
        db_id = orig_create(gym_url, sql_file_path)
        if db_id:
            _STATE["run_counter"] += 1
            run_dir = _STATE["output_root"] / f"run_{_STATE['run_counter']}"
            run_dir.mkdir(parents=True, exist_ok=True)
            # Register before dumping: if the post-seed dump itself raises,
            # the delete-time lookup below must still find this run_dir so a
            # final_state dump is still attempted -- the resulting one-sided
            # gap (final present, post_seed absent) is exactly what the
            # collector's INVALID_MISSING_DUMP check exists to catch.
            _STATE["pending_final"][db_id] = run_dir
            dump = dump_all_tables(gym_url, db_id, _headers_for(gym_url))
            write_gzip_json(dump, run_dir / "post_seed_state.json.gz")
        return db_id

    def wrapped_delete_database(gym_url: str, database_id: str) -> bool:
        run_dir = _STATE["pending_final"].pop(database_id, None)
        try:
            if run_dir is not None:
                dump = dump_all_tables(gym_url, database_id, _headers_for(gym_url))
                write_gzip_json(dump, run_dir / "final_state.json.gz")
        finally:
            # Always run the real cleanup, even if our own dump raised above,
            # so a dump failure never leaks a server-side database.
            result = orig_delete(gym_url, database_id)
        if run_dir is None:
            raise EOGPatchError(
                f"database_id {database_id!r} reached delete_database without a "
                f"tracked run directory (no post_seed dump was ever recorded for "
                f"it). The database was still deleted -- cleanup is preserved -- "
                f"but no final_state dump could be written. This means the "
                f"create/delete correlation assumption (one task per process, "
                f"--concurrency 1, task number_of_runs=1) was violated, or EOG's "
                f"cleanup logic drifted."
            )
        return result

    executor_mod.create_database_from_file = wrapped_create_database_from_file
    executor_mod.delete_database = wrapped_delete_database
    _STATE["patched"] = True
    logger.info(
        "agentrelbench: patched benchmark.executor.{create_database_from_file,delete_database}"
    )
