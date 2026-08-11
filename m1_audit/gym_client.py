"""
Shared client helpers for the M1 EnterpriseOps-Gym reproducibility audit.

Reuses benchmark/mcp_client.py from the vendored clone (create_database_from_file,
delete_database, MCPClient) for seeding/deleting DBs and for MCP tools/list + tools/call.
sql_runner() is a thin wrapper matching the exact request shape used by
benchmark/verifier.py:VerifierEngine._execute_sql_query (POST /api/sql-runner),
since mcp_client.py itself has no standalone sql-runner helper (only seed-database
and delete-database are exposed there).

Run all m1_audit scripts with the clone's venv python:
  external/EnterpriseOps-Gym/.venv/bin/python
"""
import sys
import os

CLONE_ROOT = str(_REPO / "external/EnterpriseOps-Gym")
if CLONE_ROOT not in sys.path:
    sys.path.insert(0, CLONE_ROOT)

import httpx  # noqa: E402
from benchmark.mcp_client import create_database_from_file, delete_database, MCPClient  # noqa: E402
from pathlib import Path

# Repo root, derived rather than hardcoded so the script runs from any checkout.
_REPO = Path(__file__).resolve().parent.parent

CSM_URL = "http://localhost:8001"
ITSM_URL = "http://localhost:8006"

GYM_DBS_ROOT = str(_REPO / "scratch/gym_dbs" / "Domain Wise DBs and Task-DB Mappings")
CSM_SEED = os.path.join(GYM_DBS_ROOT, "csm/dbs/db_1762232091750_3ev7dns6b.sql")
ITSM_SEED = os.path.join(GYM_DBS_ROOT, "itsm/dbs/db_1765301900121_3mwjj54xy.sql")


def seed(base_url: str, sql_path: str) -> str:
    """POST {base_url}/api/seed-database via the repo's own create_database_from_file().
    Returns the freshly-generated database_id (db_<epoch_ms>_<9 random chars>)."""
    db_id = create_database_from_file(base_url, sql_path)
    if not db_id:
        raise RuntimeError(f"seed failed for {sql_path} against {base_url}")
    return db_id


def delete_db(base_url: str, database_id: str) -> bool:
    """DELETE {base_url}/api/delete-database."""
    return delete_database(base_url, database_id)


def sql_runner(base_url: str, query: str, database_id: str, timeout: float = 60.0) -> dict:
    """POST {base_url}/api/sql-runner. Request shape mirrors verifier.py:_execute_sql_query."""
    headers = {"Content-Type": "application/json", "x-database-id": database_id}
    payload = {"query": query, "database_id": database_id}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{base_url.rstrip('/')}/api/sql-runner", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


def rows_from_sql_result(result) -> list:
    """Normalize a sql-runner JSON response into a list of row-dicts."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "rows"):
            if key in result and isinstance(result[key], list):
                return result[key]
        if "result" in result:
            return rows_from_sql_result(result["result"])
    raise ValueError(f"Unrecognized sql-runner response shape: {result!r}"[:500])


async def new_client(base_url: str, database_id: str = None, context: dict = None) -> MCPClient:
    """Create + initialize (MCP handshake) a client, ready for list_tools()/call_tool().
    Reuse the SAME client instance across a sequence of calls so the captured
    mcp-session-id persists, exactly as the harness does per-run (executor.py)."""
    client = MCPClient(base_url=base_url, database_id=database_id, context=context)
    ok = await client.connect()
    if not ok:
        raise RuntimeError(f"MCP initialize failed for {base_url}")
    return client
