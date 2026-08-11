"""
M4 TEST B, READ PURITY (csm)

On a single fresh seed, full-dump every table, call every READ-ONLY tool in
the csm union (data/eog/tool-union-csm.json, 24 tools) exactly once with
valid hardcoded arguments, then full-dump again. States must be IDENTICAL
modulo NOTHING -- unlike Test A, no volatile-column allowance here: reads must
not write, and even a timestamp bump would be a finding (per instructions).

Uses raw byte-for-byte hash comparison (db_diff.hash_canonical), not the
positional_diff_multi/volatile-stripping machinery from Test A, since the
expectation here is stricter (zero tolerance).

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/test_b_read_purity_csm.py
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, str(_REPO / "m1_audit"))
import gym_client as gc
import db_diff as dd
from pathlib import Path

# Repo root, derived rather than hardcoded so the script runs from any checkout.
_REPO = Path(__file__).resolve().parent.parent

EVIDENCE_DIR = str(_REPO / "m4_reaudit/evidence")
DATA_DIR = str(_REPO / "data/eog")

READ_ONLY_UNION = json.load(open(f"{DATA_DIR}/tool-union-csm.json"))["read_only_tools"]

# valid hardcoded arguments per tool, grounded in probe_seed_entities.py findings
CALLS = [
    ("count_case_by_state", {}),
    ("count_case_for_assignment_group", {"assignment_group_id": 4}),
    ("count_contract_by_status", {}),
    ("count_installed_product_by_status", {}),
    ("count_notifications_by_case", {"case_id": 1232}),
    ("count_notifications_by_status", {"status": "success"}),
    ("find_account", {"name": "Acme Systems"}),
    ("find_case_knowledge_linkages", {"case_id": 1232}),
    ("find_case_slas", {"case_id": 1232}),
    ("find_contracts", {"account_id": 1}),
    ("find_entitlements", {"account_id": 1}),
    ("find_installed_product_by_serial", {"serial_number": "P128-889629-8734"}),
    ("find_interactions", {"case_id": 1}),
    ("find_notifications", {"case_id": 1232}),
    ("find_product", {"name": "Windows Server 2022 Datacenter"}),
    ("find_product_by_id", {"product_id": 1}),
    ("find_products", {"category": "software"}),
    ("find_sla_definitions", {"sla_def_id": 1}),
    ("find_user_group", {"name": "Case Assignment"}),
    ("get_accounts", {"account_id": 1}),
    ("get_cases_assigned_to", {"assignment_group_id": 4}),
    ("retrieve_installed_products", {"account_id": 1}),
    ("retrieve_knowledge", {"knowledge_id": 1}),
    ("search_cases", {"case_id": 1}),
]


def extract_result(call_result):
    if not call_result.get("success"):
        return False, call_result.get("error")
    inner = call_result.get("result") or {}
    is_error = inner.get("isError", False)
    content = inner.get("content") or []
    text = content[0]["text"] if content else None
    parsed = text
    if text is not None:
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
    return (not is_error), parsed


async def main():
    t0 = time.time()
    assert sorted(t for t, _ in CALLS) == sorted(READ_ONLY_UNION), (
        f"CALLS list doesn't match the read-only union! "
        f"missing={set(READ_ONLY_UNION) - {t for t, _ in CALLS}} extra={ {t for t, _ in CALLS} - set(READ_ONLY_UNION)}"
    )

    db_id = gc.seed(gc.CSM_URL, gc.CSM_SEED)
    print(f"seeded {db_id}")

    dump_before = dd.dump_all_tables(gc.CSM_URL, db_id)
    print(f"dump_before: {len(dump_before)} tables, {dd.total_rows(dump_before)} rows")

    # thomas.green@servicenow.com (user_id=1) actor context, same as Test A / M1
    client = await gc.new_client(gc.CSM_URL, database_id=db_id, context={"x-user-email": "thomas.green@servicenow.com"})
    log = []
    for tool, args in CALLS:
        res = await client.call_tool(tool, args, database_id=db_id)
        ok, parsed = extract_result(res)
        log.append({"tool": tool, "arguments": args, "ok": ok, "result_type": type(parsed).__name__})
        if not ok:
            raise RuntimeError(f"read-only tool call FAILED (should have been valid args): {tool} args={args} -> {parsed}")

    dump_after = dd.dump_all_tables(gc.CSM_URL, db_id)
    print(f"dump_after: {len(dump_after)} tables, {dd.total_rows(dump_after)} rows")

    canon_before, canon_after = dd.canonicalize_dump(dump_before), dd.canonicalize_dump(dump_after)
    hash_before, hash_after = dd.hash_canonical(canon_before), dd.hash_canonical(canon_after)
    overall_match = hash_before["overall"] == hash_after["overall"]
    per_table_mismatches = sorted(
        t for t in hash_before["per_table"] if hash_before["per_table"].get(t) != hash_after["per_table"].get(t)
    )

    print(f"\nOVERALL hash match (before vs after {len(CALLS)} read-only calls): {overall_match}")
    print(f"  before: {hash_before['overall']}")
    print(f"  after:  {hash_after['overall']}")

    diff_report = None
    if not overall_match:
        diff_report = dd.positional_diff(dump_before, dump_after, label_a="before", label_b="after")
        print(f"  tables with differing hash: {per_table_mismatches}")
        print(f"  cell diffs ({len(diff_report['cell_diffs'])}): {diff_report['cell_diffs'][:20]}")

    evidence = {
        "test": "B_read_purity_csm",
        "read_only_union": READ_ONLY_UNION,
        "read_only_union_count": len(READ_ONLY_UNION),
        "tools_called": [c[0] for c in CALLS],
        "coverage_complete": sorted(c[0] for c in CALLS) == sorted(READ_ONLY_UNION),
        "db_id": db_id,
        "call_log": log,
        "hash_before": hash_before,
        "hash_after": hash_after,
        "overall_match": overall_match,
        "per_table_mismatches": per_table_mismatches,
        "positional_diff": diff_report,
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(f"{EVIDENCE_DIR}/test_b_csm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote evidence -> {EVIDENCE_DIR}/test_b_csm.json")

    gc.delete_db(gc.CSM_URL, db_id)
    print(f"cleaned up. Total wall time: {time.time() - t0:.2f}s")

    print("\nVERDICT:", "PASS (reads did not mutate state, zero tolerance)" if overall_match else "FAIL (see evidence -- a read tool wrote!)")


if __name__ == "__main__":
    asyncio.run(main())
