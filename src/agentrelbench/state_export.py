"""
Shared state-export module for AgentRelBench (also used by the future M2
damage labeler -- kept free of any EnterpriseOps-Gym import so it runs
identically in our own venv or the clone's venv).

Dumps full per-database state from an EnterpriseOps-Gym MCP server's
/api/sql-runner endpoint, with the two hard-won lessons from the M1
reproducibility audit (docs/M1-audit-evidence.md, Test 4) baked in:

1. The sql-runner endpoint silently appends "LIMIT 100" to any query that
   doesn't already carry its own LIMIT clause -- discoverable only by
   inspecting the echoed `query` field in the response. Every dump query
   here therefore carries an explicit, large LIMIT, and the returned row
   count is asserted to be strictly below that LIMIT: a returned count
   *equal to* the LIMIT is indistinguishable from silent truncation, so it
   is always treated as an error rather than a coincidental exact match
   (see `assert_not_truncated`).
2. Per-domain auth differs: csm's tools (and, per benchmark/verifier.py's
   own sql-runner call, its verifier state-diff queries) require headers
   built from the task's `gym_servers_config[].context` dict (e.g.
   `x-user-email`); itsm needs none. Rather than hard-coding per-domain
   logic, this module takes `headers` as an explicit parameter -- callers
   derive it from the task JSON via `context_to_headers()`, which mirrors
   benchmark/mcp_client.py's own context-to-header conversion exactly.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

DEFAULT_LIMIT = 1_000_000


class DumpTruncatedError(RuntimeError):
    """Raised when a table's returned row count hit the configured LIMIT.

    A returned row count == limit is indistinguishable from a silently
    truncated result (docs/M1-audit-evidence.md Test 4: the server silently
    applies LIMIT 100 to any query without its own LIMIT), so it is always
    treated as truncation rather than assumed to be a coincidental exact
    match.
    """


def assert_not_truncated(table: str, row_count: int, limit: int) -> None:
    """Raise DumpTruncatedError if `row_count` hit `limit` (see class docstring
    on DumpTruncatedError for why `==` -- not just `>` -- counts as truncated)."""
    if row_count >= limit:
        raise DumpTruncatedError(
            f"table '{table}': sql-runner returned {row_count} rows for an "
            f"explicit LIMIT {limit}. A count equal to the limit cannot be "
            f"trusted as the true total (docs/M1-audit-evidence.md Test 4 found "
            f"the server silently applies LIMIT 100 to any query lacking its own "
            f"LIMIT clause) -- increase `limit` and retry."
        )


def context_to_headers(context: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Convert a gym `context` dict (e.g. {"x-user-email": "..."}) into HTTP
    headers, exactly mirroring the conversion in benchmark/mcp_client.py's
    MCPClient._send_request / benchmark/verifier.py's _execute_sql_query:
    keys already starting with "x-" pass through as-is; everything else
    becomes "x-<key, underscores->hyphens, lowercased>"."""
    headers: Dict[str, str] = {}
    for key, value in (context or {}).items():
        if key.lower().startswith("x-"):
            header_key = key
        else:
            header_key = f"x-{key.lower().replace('_', '-')}"
        headers[header_key] = str(value)
    return headers


def _rows_from_result(result: Any) -> List[dict]:
    """Normalize a /api/sql-runner JSON response into a list of row-dicts.
    Deliberately independent of m1_audit/gym_client.py's identical helper
    (m1_audit/ is read-only reference material, not a dependency)."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "rows"):
            value = result.get(key)
            if isinstance(value, list):
                return value
        if "result" in result:
            return _rows_from_result(result["result"])
    raise ValueError(f"Unrecognized sql-runner response shape: {result!r}"[:500])


def sql_runner(
    server_url: str,
    query: str,
    database_id: str,
    headers: Dict[str, str],
    timeout: float = 60.0,
) -> List[dict]:
    """POST {server_url}/api/sql-runner and return the normalized row list.

    Request shape mirrors benchmark/verifier.py:_execute_sql_query: JSON body
    {query, database_id}, plus an `x-database-id` header and whatever
    per-gym `headers` the caller supplies (already converted via
    context_to_headers).
    """
    url = f"{server_url.rstrip('/')}/api/sql-runner"
    payload = {"query": query, "database_id": database_id}
    request_headers = {"Content-Type": "application/json", "x-database-id": database_id}
    request_headers.update(headers or {})
    response = httpx.post(url, json=payload, headers=request_headers, timeout=timeout)
    response.raise_for_status()
    return _rows_from_result(response.json())


def list_tables(
    server_url: str,
    database_id: str,
    headers: Dict[str, str],
    limit: int = DEFAULT_LIMIT,
) -> List[str]:
    """Enumerate table names via sqlite_master, sorted alphabetically
    (canonical table ordering)."""
    rows = sql_runner(
        server_url,
        f"SELECT name FROM sqlite_master WHERE type='table' LIMIT {limit};",
        database_id,
        headers,
    )
    assert_not_truncated("sqlite_master", len(rows), limit)
    return sorted(row["name"] for row in rows)


def dump_table(
    server_url: str,
    database_id: str,
    table: str,
    headers: Dict[str, str],
    limit: int = DEFAULT_LIMIT,
) -> List[dict]:
    """Dump every row of one table with an explicit LIMIT, in the server's
    natural (unsorted) row order. Natural order is preserved deliberately --
    not re-sorted -- so a future positional diff (M1 audit's db_diff.py
    approach) can align rows across replicas without a volatile column's
    scrambled sort order breaking the alignment."""
    rows = sql_runner(server_url, f"SELECT * FROM {table} LIMIT {limit};", database_id, headers)
    assert_not_truncated(table, len(rows), limit)
    return rows


def dump_all_tables(
    server_url: str,
    database_id: str,
    headers: Dict[str, str],
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """Dump every table in `database_id` via /api/sql-runner.

    Returns {"database_id": database_id, "tables": {name: [row_dict, ...]}}
    with table names in canonical (sorted) order and rows in natural DB
    order. Every query carries an explicit LIMIT and asserts the returned
    count is below it (see assert_not_truncated).
    """
    tables = list_tables(server_url, database_id, headers, limit=limit)
    return {
        "database_id": database_id,
        "tables": {
            table: dump_table(server_url, database_id, table, headers, limit=limit)
            for table in tables
        },
    }


def write_gzip_json(obj: Any, path: Union[str, Path]) -> None:
    """Write `obj` as gzip-compressed JSON, with dict keys sorted at every
    level (canonical, reproducible byte output -- this is what makes a
    straight `==` comparison of two decoded dumps meaningful) and a fixed
    gzip mtime=0 so identical content produces byte-identical files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(payload)


def read_gzip_json(path: Union[str, Path]) -> Any:
    """Inverse of write_gzip_json."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)
