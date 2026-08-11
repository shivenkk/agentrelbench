"""
M4 TEST B, READ PURITY (itsm)

Same protocol as test_b_read_purity_csm.py: fresh seed, full dump, call every
READ-ONLY tool in the itsm union (data/eog/tool-union-itsm.json, 18 tools)
once with valid hardcoded args, dump again, zero-tolerance hash comparison.

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/test_b_read_purity_itsm.py
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/Users/shiven/Documents/Projects/agentrelbench/m1_audit")
import gym_client as gc
import db_diff as dd

EVIDENCE_DIR = "/Users/shiven/Documents/Projects/agentrelbench/m4_reaudit/evidence"
DATA_DIR = "/Users/shiven/Documents/Projects/agentrelbench/data/eog"

READ_ONLY_UNION = json.load(open(f"{DATA_DIR}/tool-union-itsm.json"))["read_only_tools"]

CALLS = [
    ("find_change_by_number", {"number": "CHG0000001"}),
    ("find_change_request_mappings_for_incident", {"incident_id": "INC_001"}),
    ("find_configuration_item_by_serial_number", {"serial_number": "LAPTOP-NYC-001"}),
    ("find_configuration_items", {"status": "in_use"}),
    ("find_incident_by_id", {"incident_id": "INC_001"}),
    ("find_incident_by_number", {"number": "INC0000001"}),
    ("find_incident_slas", {"incident_id": "INC_001"}),
    ("find_notifications_sent_for_incident", {"incident_id": "INC_001"}),
    ("find_parent_incident", {"child_incident": "INC_001"}),
    ("find_stage_wise_breached_incident_sla_counts", {"stages": ["breached", "completed"]}),
    ("get_incident_template_by_name", {"name": "Password Reset Template"}),
    ("get_incident_templates", {"active": True}),
    ("get_user", {"user_id": "USER_001"}),
    ("get_user_using_name", {"first_name": "Marcus", "last_name": "Thompson"}),
    ("list_change_request_mappings", {"change_id": "CHG_001"}),
    ("list_changes", {"status": "closed"}),
    ("list_child_incidents", {"parent_incident": "INC_006"}),
    ("list_incidents", {"status": "new"}),
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

    db_id = gc.seed(gc.ITSM_URL, gc.ITSM_SEED)
    print(f"seeded {db_id}")

    dump_before = dd.dump_all_tables(gc.ITSM_URL, db_id)
    print(f"dump_before: {len(dump_before)} tables, {dd.total_rows(dump_before)} rows")

    client = await gc.new_client(gc.ITSM_URL, database_id=db_id)  # no context needed, per M1
    log = []
    for tool, args in CALLS:
        res = await client.call_tool(tool, args, database_id=db_id)
        ok, parsed = extract_result(res)
        log.append({"tool": tool, "arguments": args, "ok": ok, "result_type": type(parsed).__name__})
        if not ok:
            raise RuntimeError(f"read-only tool call FAILED (should have been valid args): {tool} args={args} -> {parsed}")

    dump_after = dd.dump_all_tables(gc.ITSM_URL, db_id)
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
        "test": "B_read_purity_itsm",
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
    with open(f"{EVIDENCE_DIR}/test_b_itsm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote evidence -> {EVIDENCE_DIR}/test_b_itsm.json")

    gc.delete_db(gc.ITSM_URL, db_id)
    print(f"cleaned up. Total wall time: {time.time() - t0:.2f}s")

    print("\nVERDICT:", "PASS (reads did not mutate state, zero tolerance)" if overall_match else "FAIL (see evidence -- a read tool wrote!)")


if __name__ == "__main__":
    asyncio.run(main())
