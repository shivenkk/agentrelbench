"""
TEST 2 — SEED REPEATABILITY (csm)

Load the same csm seed SQL file twice (two independent POST /api/seed-database
calls -> two database_ids), enumerate tables via sql-runner, dump every table
from both, canonicalize (sorted tables, rows sorted by all columns, no columns
excluded), hash, and compare. If not identical, report exactly which
table.column values differ.

Rerun: /path/to/.venv/bin/python m1_audit/test2_seed_repeatability.py
"""
import json
import sys
import time

sys.path.insert(0, "/Users/shiven/Documents/Projects/agentrelbench/m1_audit")
import gym_client as gc
import db_diff as dd

EVIDENCE = "/Users/shiven/Documents/Projects/agentrelbench/m1_audit/evidence/test2_seed_repeatability.json"


def main():
    t0 = time.time()
    db1 = gc.seed(gc.CSM_URL, gc.CSM_SEED)
    db2 = gc.seed(gc.CSM_URL, gc.CSM_SEED)
    print(f"seeded db1={db1} db2={db2} (seed file: {gc.CSM_SEED})")

    tables1 = dd.get_tables(gc.CSM_URL, db1)
    tables2 = dd.get_tables(gc.CSM_URL, db2)
    tables_match = tables1 == tables2
    print(f"table list identical across the two seeds: {tables_match} ({len(tables1)} tables)")

    dump1 = dd.dump_all_tables(gc.CSM_URL, db1, tables1)
    dump2 = dd.dump_all_tables(gc.CSM_URL, db2, tables2)
    n1, n2 = dd.total_rows(dump1), dd.total_rows(dump2)
    print(f"total rows: db1={n1} db2={n2}")

    canon1 = dd.canonicalize_dump(dump1)
    canon2 = dd.canonicalize_dump(dump2)
    hash1 = dd.hash_canonical(canon1)
    hash2 = dd.hash_canonical(canon2)

    overall_match = hash1["overall"] == hash2["overall"]
    per_table_mismatches = sorted(
        t for t in hash1["per_table"] if hash1["per_table"].get(t) != hash2["per_table"].get(t)
    )

    print(f"\nOVERALL canonical hash match: {overall_match}")
    print(f"  db1 overall hash: {hash1['overall']}")
    print(f"  db2 overall hash: {hash2['overall']}")
    if per_table_mismatches:
        print(f"  tables with differing hash: {per_table_mismatches}")
    else:
        print("  no per-table hash mismatches")

    diff_report = None
    varying = {}
    if not overall_match:
        # raw (natural DB order) positional diff pinpoints exact table.column
        diff_report = dd.positional_diff(dump1, dump2, label_a="db1", label_b="db2")
        varying = dd.varying_columns_summary(diff_report["cell_diffs"])
        print(f"\nPositional diff: row_count_mismatch={diff_report['row_count_mismatch']}")
        print(f"Varying table.column keys: {sorted(varying.keys())}")

    evidence = {
        "seed_file": gc.CSM_SEED,
        "db1": db1,
        "db2": db2,
        "tables_identical_set": tables_match,
        "tables": tables1,
        "total_rows_db1": n1,
        "total_rows_db2": n2,
        "hash_db1": hash1,
        "hash_db2": hash2,
        "overall_match": overall_match,
        "per_table_mismatches": per_table_mismatches,
        "positional_diff": diff_report,
        "varying_columns": varying,
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(EVIDENCE, "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote evidence -> {EVIDENCE}")

    gc.delete_db(gc.CSM_URL, db1)
    gc.delete_db(gc.CSM_URL, db2)
    print(f"cleaned up db1, db2. Total wall time: {time.time() - t0:.2f}s")

    print("\nVERDICT:", "PASS (identical)" if overall_match else "FAIL (differs, see evidence)")


if __name__ == "__main__":
    main()
