"""
TEST 4, SQL-RUNNER SURFACE (csm)

Confirms: multi-table SELECT/JOIN support, sqlite_master accessibility,
the implicit-LIMIT-100 truncation behavior and how to avoid it, and times a
full dump of every csm table to establish that a per-run full-state export is
cheap.

Rerun: /path/to/.venv/bin/python m1_audit/test4_sql_runner_surface.py
"""
import json
import sys
import time

sys.path.insert(0, str(_REPO / "m1_audit"))
import gym_client as gc
import db_diff as dd
from pathlib import Path

# Repo root, derived rather than hardcoded so the script runs from any checkout.
_REPO = Path(__file__).resolve().parent.parent

EVIDENCE = str(_REPO / "m1_audit/evidence/test4_sql_runner_surface.json")


def main():
    evidence = {}
    db_id = gc.seed(gc.CSM_URL, gc.CSM_SEED)
    print("seeded db_id:", db_id)
    evidence["db_id"] = db_id

    # 1. sqlite_master accessibility
    r = gc.sql_runner(gc.CSM_URL, "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1000;", db_id)
    tables = [row["name"] for row in gc.rows_from_sql_result(r)]
    evidence["sqlite_master_accessible"] = True
    evidence["tables"] = tables
    print(f"sqlite_master accessible: True ({len(tables)} tables)")

    # 2. JOIN support (multi-table, with aliases and AS)
    join_q = (
        "SELECT cc.case_id, cc.state, u.first_name, u.last_name "
        "FROM customer_case cc LEFT JOIN \"user\" u ON cc.assigned_to = u.user_id "
        "LIMIT 5;"
    )
    r_join = gc.sql_runner(gc.CSM_URL, join_q, db_id)
    join_rows = gc.rows_from_sql_result(r_join)
    evidence["join_supported"] = True
    evidence["join_sample"] = join_rows
    print(f"JOIN supported: True (sample: {join_rows[:2]})")

    # 3. 3-table join + aggregate (GROUP BY)
    agg_q = (
        "SELECT a.name AS account_name, COUNT(cc.case_id) AS case_count "
        "FROM account a "
        "JOIN customer_case cc ON cc.account_id = a.account_id "
        "JOIN contract ct ON ct.account_id = a.account_id "
        "GROUP BY a.account_id LIMIT 5;"
    )
    try:
        r_agg = gc.sql_runner(gc.CSM_URL, agg_q, db_id)
        agg_rows = gc.rows_from_sql_result(r_agg)
        evidence["three_table_join_and_group_by_supported"] = True
        evidence["three_table_join_sample"] = agg_rows
        print(f"3-table JOIN + GROUP BY supported: True (sample: {agg_rows[:2]})")
    except Exception as e:
        evidence["three_table_join_and_group_by_supported"] = False
        evidence["three_table_join_error"] = str(e)
        print(f"3-table JOIN + GROUP BY supported: False ({e})")

    # 4. Non-SELECT rejected (read-only enforcement)
    try:
        gc.sql_runner(gc.CSM_URL, "PRAGMA table_info(customer_case);", db_id)
        evidence["pragma_rejected"] = False
    except Exception as e:
        evidence["pragma_rejected"] = True
        evidence["pragma_rejection_message"] = str(e)
        print(f"PRAGMA (non-SELECT) rejected: True ({e})")

    # 5. implicit LIMIT 100 truncation behavior on the largest table
    counts = {t: gc.rows_from_sql_result(gc.sql_runner(gc.CSM_URL, f"SELECT COUNT(*) AS cnt FROM {t};", db_id))[0]["cnt"] for t in tables}
    biggest = max(counts, key=lambda k: counts[k])
    evidence["row_counts"] = counts
    evidence["biggest_table"] = biggest
    evidence["biggest_table_row_count"] = counts[biggest]

    r_nolimit = gc.sql_runner(gc.CSM_URL, f"SELECT * FROM {biggest};", db_id)
    n_nolimit = len(gc.rows_from_sql_result(r_nolimit))
    echoed_query = r_nolimit.get("query", "")
    evidence["implicit_limit_truncation"] = {
        "query_sent": f"SELECT * FROM {biggest};",
        "rows_returned_without_explicit_limit": n_nolimit,
        "echoed_query_from_server": echoed_query,
        "truncated": n_nolimit < counts[biggest],
    }
    print(f"Implicit LIMIT truncation on '{biggest}' ({counts[biggest]} rows): "
          f"no-LIMIT query returned {n_nolimit} rows; server echoed query = {echoed_query!r}")

    r_biglimit = gc.sql_runner(gc.CSM_URL, f"SELECT * FROM {biggest} LIMIT 1000000;", db_id)
    n_biglimit = len(gc.rows_from_sql_result(r_biglimit))
    evidence["explicit_limit_override"] = {
        "query_sent": f"SELECT * FROM {biggest} LIMIT 1000000;",
        "rows_returned": n_biglimit,
        "matches_true_row_count": n_biglimit == counts[biggest],
    }
    print(f"Explicit LIMIT 1000000 override: returned {n_biglimit} rows (true count {counts[biggest]}) -> "
          f"{'NOT truncated' if n_biglimit == counts[biggest] else 'STILL TRUNCATED'}")

    # 6. time a full dump of ALL csm tables (using the same explicit-big-LIMIT
    #    helper that tests 2/3/5 rely on, so this timing is representative)
    t0 = time.time()
    full_dump = dd.dump_all_tables(gc.CSM_URL, db_id, tables)
    wall_time = time.time() - t0
    total = dd.total_rows(full_dump)
    evidence["full_dump_timing"] = {
        "wall_time_s": round(wall_time, 3),
        "total_tables": len(tables),
        "total_rows": total,
        "avg_ms_per_table": round(wall_time / len(tables) * 1000, 2),
    }
    print(f"\nFull dump of {len(tables)} tables / {total} rows took {wall_time:.3f}s "
          f"({wall_time / len(tables) * 1000:.2f} ms/table avg)")

    with open(EVIDENCE, "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote evidence -> {EVIDENCE}")

    gc.delete_db(gc.CSM_URL, db_id)
    print("cleaned up db_id:", db_id)

    print("\nVERDICT: PASS" if (evidence["join_supported"] and evidence["sqlite_master_accessible"]
                                 and evidence["explicit_limit_override"]["matches_true_row_count"])
          else "\nVERDICT: PARTIAL/FAIL (see evidence)")


if __name__ == "__main__":
    main()
