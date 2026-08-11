"""
Shared table-dump / canonicalize / hash / diff helpers used by tests 2, 3, 5.

sql-runner is SELECT-only (PRAGMA is rejected: "Only read-only SELECT queries
are allowed" - confirmed empirically) and silently applies an implicit
LIMIT 100 to any query without its own LIMIT clause (also confirmed empirically:
the echoed `query` field showed the injected "LIMIT 100"). An explicit larger
LIMIT overrides it (tested up to 100000 against a 2464-row table). So every
dump query here carries an explicit large LIMIT. Since PRAGMA table_info is
blocked, primary-key discovery instead parses the CREATE TABLE text exposed via
`SELECT sql FROM sqlite_master`.
"""
import hashlib
import json
import re
import sys

sys.path.insert(0, str(_REPO / "m1_audit"))
import gym_client as gc
from pathlib import Path

# Repo root, derived rather than hardcoded so the script runs from any checkout.
_REPO = Path(__file__).resolve().parent.parent

BIG_LIMIT = 1_000_000


def get_tables(base_url: str, db_id: str) -> list:
    r = gc.sql_runner(base_url, f"SELECT name FROM sqlite_master WHERE type='table' LIMIT {BIG_LIMIT};", db_id)
    rows = gc.rows_from_sql_result(r)
    return sorted(row["name"] for row in rows)


def get_table_schema_sql(base_url: str, db_id: str, table: str):
    r = gc.sql_runner(
        base_url,
        f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}' LIMIT 5;",
        db_id,
    )
    rows = gc.rows_from_sql_result(r)
    return rows[0]["sql"] if rows else None


_PK_RE = re.compile(r'"?(\w+)"?\s+INTEGER\s+PRIMARY\s+KEY', re.IGNORECASE)


def get_pk_column(base_url: str, db_id: str, table: str):
    """Best-effort single-column INTEGER PRIMARY KEY name, parsed from the
    CREATE TABLE text (PRAGMA table_info is blocked by the sql-runner)."""
    sql_text = get_table_schema_sql(base_url, db_id, table)
    if not sql_text:
        return None
    m = _PK_RE.search(sql_text)
    return m.group(1) if m else None


def dump_table(base_url: str, db_id: str, table: str, limit: int = BIG_LIMIT) -> list:
    r = gc.sql_runner(base_url, f"SELECT * FROM {table} LIMIT {limit};", db_id)
    return gc.rows_from_sql_result(r)


def dump_all_tables(base_url: str, db_id: str, tables: list = None) -> dict:
    tables = tables if tables is not None else get_tables(base_url, db_id)
    return {t: dump_table(base_url, db_id, t) for t in tables}


def total_rows(dump: dict) -> int:
    return sum(len(rows) for rows in dump.values())


def _row_sort_key(row: dict) -> str:
    return json.dumps(row, sort_keys=True, default=str)


def canonicalize_dump(dump: dict) -> dict:
    """Sorted tables (dict insertion order == sorted keys), rows within each
    table sorted by their full-row canonical JSON string. No columns excluded."""
    return {table: sorted(dump[table], key=_row_sort_key) for table in sorted(dump.keys())}


def hash_canonical(canon: dict) -> dict:
    per_table = {
        table: hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
        for table, rows in canon.items()
    }
    overall = hashlib.sha256(json.dumps(canon, sort_keys=True, default=str).encode()).hexdigest()
    return {"overall": overall, "per_table": per_table}


def positional_diff(dump_a: dict, dump_b: dict, label_a: str = "A", label_b: str = "B") -> dict:
    """Compare two RAW (natural DB order, NOT sorted) dumps table-by-table,
    row-position by row-position. Valid when both dumps result from identical
    operation sequences (same seed file, same tool-call order), so physical
    row order should match even though values in specific columns may not.
    This is what actually answers 'which table.column differs' without the
    volatile column itself scrambling row alignment (which sorting would do)."""
    report = {
        "tables_only_in_a": [],
        "tables_only_in_b": [],
        "row_count_mismatch": {},
        "cell_diffs": [],
    }
    tables_a, tables_b = set(dump_a), set(dump_b)
    report["tables_only_in_a"] = sorted(tables_a - tables_b)
    report["tables_only_in_b"] = sorted(tables_b - tables_a)
    for table in sorted(tables_a & tables_b):
        rows_a, rows_b = dump_a[table], dump_b[table]
        if len(rows_a) != len(rows_b):
            report["row_count_mismatch"][table] = {label_a: len(rows_a), label_b: len(rows_b)}
            continue
        for i, (ra, rb) in enumerate(zip(rows_a, rows_b)):
            for col in sorted(set(ra) | set(rb)):
                va, vb = ra.get(col, "<MISSING_COL>"), rb.get(col, "<MISSING_COL>")
                if va != vb:
                    report["cell_diffs"].append(
                        {"table": table, "column": col, "row_index": i, label_a: va, label_b: vb}
                    )
    return report


def varying_columns_summary(cell_diffs: list) -> dict:
    """Aggregate a positional_diff()'s cell_diffs into per table.column stats
    with a few example (before/after) values, for the volatile-columns JSON."""
    agg = {}
    for d in cell_diffs:
        key = f"{d['table']}.{d['column']}"
        entry = agg.setdefault(key, {"table": d["table"], "column": d["column"], "diff_count": 0, "examples": []})
        entry["diff_count"] += 1
        if len(entry["examples"]) < 3:
            entry["examples"].append({k: v for k, v in d.items() if k not in ("table", "column")})
    return agg


def positional_diff_multi(dumps: dict) -> dict:
    """N-way version of positional_diff: dumps = {label: {table: [rows]}}.
    Compares every replica's tables position-by-position (natural DB order)."""
    labels = list(dumps.keys())
    table_sets = [set(dumps[l].keys()) for l in labels]
    common_tables = set.intersection(*table_sets) if table_sets else set()
    all_tables = set.union(*table_sets) if table_sets else set()
    report = {
        "labels": labels,
        "tables_not_common_to_all": sorted(all_tables - common_tables),
        "row_count_mismatch": {},
        "cell_diffs": [],
    }
    for table in sorted(common_tables):
        lengths = {l: len(dumps[l][table]) for l in labels}
        if len(set(lengths.values())) > 1:
            report["row_count_mismatch"][table] = lengths
            continue
        n = lengths[labels[0]]
        for i in range(n):
            rows = {l: dumps[l][table][i] for l in labels}
            cols = set()
            for r in rows.values():
                cols |= set(r.keys())
            for col in sorted(cols):
                vals = {l: rows[l].get(col, "<MISSING_COL>") for l in labels}
                serialized = {json.dumps(v, sort_keys=True, default=str) for v in vals.values()}
                if len(serialized) > 1:
                    report["cell_diffs"].append({"table": table, "column": col, "row_index": i, "values": vals})
    return report


_TIMESTAMP_NAME_RE = re.compile(r"(created|updated|_at$|_on$|time|timestamp)", re.IGNORECASE)
_TIMESTAMP_VALUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")
_PK_NAME_RE = re.compile(r"(^id$|_id$)", re.IGNORECASE)
_RANDOM_ID_RE = re.compile(r"^[0-9a-fA-F]{8,}(-[0-9a-fA-F]{4,}){0,4}$")


def classify_volatility(column: str, sample_values: list) -> str:
    """Heuristic label for *why* a column varies: wall-clock timestamp /
    auto-increment / random identifier / unknown (manual review needed)."""
    str_vals = [str(v) for v in sample_values if v is not None and v != "<MISSING_COL>"]
    if not str_vals:
        return "unknown"
    if _TIMESTAMP_NAME_RE.search(column) and any(_TIMESTAMP_VALUE_RE.match(v) for v in str_vals):
        return "wall-clock timestamp"
    if all(_TIMESTAMP_VALUE_RE.match(v) for v in str_vals):
        return "wall-clock timestamp"
    if _PK_NAME_RE.search(column):
        try:
            ints = [int(v) for v in str_vals]
            return "auto-increment" if ints == sorted(set(ints)) or len(set(ints)) <= len(ints) else "unknown"
        except ValueError:
            pass
    if any(_RANDOM_ID_RE.match(v) for v in str_vals):
        return "random identifier"
    return "unknown"


def varying_columns_summary_multi(cell_diffs: list) -> dict:
    """Like varying_columns_summary but for positional_diff_multi's cell_diffs
    (each has a 'values' dict keyed by replica label instead of two named keys).
    Adds a heuristic 'behavior' classification per column."""
    agg = {}
    for d in cell_diffs:
        key = f"{d['table']}.{d['column']}"
        entry = agg.setdefault(
            key, {"table": d["table"], "column": d["column"], "diff_count": 0, "examples": [], "behavior": None}
        )
        entry["diff_count"] += 1
        if len(entry["examples"]) < 5:
            entry["examples"].append({"row_index": d["row_index"], "values": d["values"]})
    for entry in agg.values():
        sample = []
        for ex in entry["examples"]:
            sample.extend(ex["values"].values())
        entry["behavior"] = classify_volatility(entry["column"], sample)
    return agg
