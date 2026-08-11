"""
TEST 5, ISOLATION (csm)

Seed two independent database_ids (A, B) from the same seed file. Using a
SINGLE MCP session (one MCPClient / one mcp-session-id, constructed with no
database_id bound at all), alternate state-changing tool calls between A and B
call-by-call, passing database_id explicitly on each call. This isolates the
routing-mechanism question: if the server keyed state off the MCP session
(server-global/session-sticky) rather than the per-call x-database-id header,
alternating within one session would show writes bleeding into the wrong
database. Because A and B are independently seeded from an identical file,
the first create_new_case against each lands on the SAME next-autoincrement
case_id in both -- a strong, unambiguous contamination probe: row content
(not just row existence) must differ correctly per database even though the
PK collides.

Rerun: /path/to/.venv/bin/python m1_audit/test5_isolation.py
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

EVIDENCE = str(_REPO / "m1_audit/evidence/test5_isolation.json")
ACTOR_EMAIL = "thomas.green@servicenow.com"


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
    db_a = gc.seed(gc.CSM_URL, gc.CSM_SEED)
    db_b = gc.seed(gc.CSM_URL, gc.CSM_SEED)
    print(f"db_a={db_a} db_b={db_b} (same seed file, independent ids)")

    before_a = dd.dump_table(gc.CSM_URL, db_a, "customer_case")
    before_b = dd.dump_table(gc.CSM_URL, db_b, "customer_case")
    print(f"customer_case row count before: A={len(before_a)} B={len(before_b)}")

    # ONE session for the whole alternating sequence -- no database_id bound
    # at construction, so every call below routes purely on its own explicit
    # database_id argument (per-call header), not on any client/session default.
    client = await gc.new_client(gc.CSM_URL, database_id=None, context={"x-user-email": ACTOR_EMAIL})
    log = []

    async def call(db_id, tool, args):
        res = await client.call_tool(tool, args, database_id=db_id)
        ok, parsed = extract_result(res)
        log.append({"routed_to_db_id": db_id, "tool": tool, "arguments": args, "ok": ok, "parsed_result": parsed})
        if not ok:
            raise RuntimeError(f"tool call failed: db={db_id} {tool} args={args} -> {parsed}")
        return parsed

    # alternating sequence: A, B, A, B, A, B (single shared MCP session throughout)
    case_a = (await call(db_a, "create_new_case", {
        "account_id": 1, "contact_id": 123, "channel": "email", "priority": "high",
        "state": "new", "short_description": "ISOLATION TEST case on A",
        "assignment_group_id": 4, "assigned_to": 3, "escalation": False,
        "product_id": 128, "installed_product_id": 3,
    }))["case_id"]

    case_b = (await call(db_b, "create_new_case", {
        "account_id": 1, "contact_id": 123, "channel": "web", "priority": "moderate",
        "state": "new", "short_description": "ISOLATION TEST case on B",
        "assignment_group_id": 4, "assigned_to": 5, "escalation": False,
        "product_id": 128, "installed_product_id": 3,
    }))["case_id"]

    await call(db_a, "update_case", {"case_id": case_a, "state": "in_progress"})
    await call(db_b, "update_case", {"case_id": case_b, "state": "pending"})
    await call(db_a, "assign_case_to_user", {"case_id": case_a, "assigned_to_user_id": 6})
    await call(db_b, "assign_case_to_user", {"case_id": case_b, "assigned_to_user_id": 9})

    print(f"case_a (created in db_a) = {case_a}; case_b (created in db_b) = {case_b}"
          f" (same session used throughout; same value would confirm both DBs started"
          f" from independent, identical autoincrement state)")

    dump_a = dd.dump_all_tables(gc.CSM_URL, db_a)
    dump_b = dd.dump_all_tables(gc.CSM_URL, db_b)

    cc_a = {row["case_id"]: row for row in dump_a["customer_case"]}
    cc_b = {row["case_id"]: row for row in dump_b["customer_case"]}

    checks = {}
    checks["case_a_present_in_db_a"] = case_a in cc_a
    checks["case_a_absent_from_db_b"] = case_a not in cc_b or cc_b.get(case_a, {}).get("short_description") != "ISOLATION TEST case on A"
    checks["case_b_present_in_db_b"] = case_b in cc_b
    checks["case_b_absent_from_db_a"] = case_b not in cc_a or cc_a.get(case_b, {}).get("short_description") != "ISOLATION TEST case on B"

    checks["db_a_case_content_correct"] = (
        case_a in cc_a
        and cc_a[case_a]["short_description"] == "ISOLATION TEST case on A"
        and cc_a[case_a]["state"] == "in_progress"
        and cc_a[case_a]["assigned_to"] == 6
    )
    checks["db_b_case_content_correct"] = (
        case_b in cc_b
        and cc_b[case_b]["short_description"] == "ISOLATION TEST case on B"
        and cc_b[case_b]["state"] == "pending"
        and cc_b[case_b]["assigned_to"] == 9
    )

    checks["row_count_delta_db_a_is_exactly_1"] = len(dump_a["customer_case"]) == len(before_a) + 1
    checks["row_count_delta_db_b_is_exactly_1"] = len(dump_b["customer_case"]) == len(before_b) + 1

    # cross-scan: make sure NEITHER isolation-test description string leaked
    # into the OTHER database anywhere in customer_case (not just at the same id)
    all_desc_a = {row["case_id"]: row.get("short_description") for row in dump_a["customer_case"]}
    all_desc_b = {row["case_id"]: row.get("short_description") for row in dump_b["customer_case"]}
    checks["no_B_description_anywhere_in_A"] = "ISOLATION TEST case on B" not in all_desc_a.values()
    checks["no_A_description_anywhere_in_B"] = "ISOLATION TEST case on A" not in all_desc_b.values()

    all_pass = all(checks.values())

    print("\nIsolation checks:")
    for k, v in checks.items():
        print(f"  {k}: {v}")

    routing_conclusion = (
        "per-call argument (x-database-id header on each tools/call request) -- "
        "confirmed empirically: a single shared MCP session correctly alternated "
        "writes between two databases call-by-call with zero cross-contamination"
        if all_pass else
        "INCONCLUSIVE/BROKEN -- see checks above, cross-contamination or routing failure detected"
    )
    print(f"\nRouting mechanism conclusion: {routing_conclusion}")

    evidence = {
        "db_a": db_a,
        "db_b": db_b,
        "case_a_id": case_a,
        "case_b_id": case_b,
        "same_pk_collision_across_independent_dbs": case_a == case_b,
        "call_log": log,
        "checks": checks,
        "all_checks_passed": all_pass,
        "routing_conclusion": routing_conclusion,
        "customer_case_row_count_before": {"A": len(before_a), "B": len(before_b)},
        "customer_case_row_count_after": {"A": len(dump_a["customer_case"]), "B": len(dump_b["customer_case"])},
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(EVIDENCE, "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote evidence -> {EVIDENCE}")

    gc.delete_db(gc.CSM_URL, db_a)
    gc.delete_db(gc.CSM_URL, db_b)
    print(f"cleaned up db_a, db_b. Total wall time: {time.time() - t0:.2f}s")

    print("\nVERDICT:", "PASS (no cross-contamination)" if all_pass else "FAIL (see evidence)")


if __name__ == "__main__":
    asyncio.run(main())
