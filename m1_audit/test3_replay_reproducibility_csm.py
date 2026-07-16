"""
TEST 3 — REPLAY REPRODUCIBILITY (csm, the key test)

Seed 3 independent csm databases from the identical seed file, then execute the
identical fixed sequence of 10 tool calls (6 distinct state-changing tools:
create_new_case, update_case, assign_case_to_user, link_new_case_sla,
send_notification, update_case_sla_details) against each. All arguments that
reference pre-existing seed entities are hardcoded, discovered via
probe_seed_ids.py (account_id=1, contact_id=123, product_id=128,
installed_product_id=3, assignment_group_id=4, agent user_ids 3/5/6/9,
sla_def_id 1/2). Arguments that reference entities CREATED during the sequence
(case_a, case_b, the two case_sla links) are captured dynamically per replica
from that replica's own tool responses -- that's the whole point: if the
server is deterministic, the captured IDs should be identical across all 3
replicas.

After the sequence, dump every table from all 3 replicas and diff position-by-
position (natural DB row order, since all 3 replicas underwent an identical
seed + identical call order, so physical row order should match even where
specific column values differ).

Rerun: /path/to/.venv/bin/python m1_audit/test3_replay_reproducibility_csm.py
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/Users/shiven/Documents/Projects/agentrelbench/m1_audit")
import gym_client as gc
import db_diff as dd

ACTOR_EMAIL = "thomas.green@servicenow.com"  # user_id=1, role=agent, present in every csm seed replica
DATA_DIR = "/Users/shiven/Documents/Projects/agentrelbench/data/eog"
EVIDENCE_DIR = "/Users/shiven/Documents/Projects/agentrelbench/m1_audit/evidence"


def extract_result(call_result):
    """Returns (ok: bool, parsed: dict|str|None) from an MCPClient.call_tool() return value."""
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


async def run_sequence(base_url: str, db_id: str) -> dict:
    client = await gc.new_client(base_url, database_id=db_id, context={"x-user-email": ACTOR_EMAIL})
    log = []

    async def call(tool, args):
        res = await client.call_tool(tool, args, database_id=db_id)
        ok, parsed = extract_result(res)
        log.append({"step": len(log) + 1, "tool": tool, "arguments": args, "ok": ok, "parsed_result": parsed})
        if not ok:
            raise RuntimeError(f"tool call failed at step {len(log)}: {tool} args={args} -> {parsed}")
        return parsed

    case_a = (await call("create_new_case", {
        "account_id": 1, "contact_id": 123, "channel": "email", "priority": "high",
        "state": "new", "short_description": "M1 replay case A",
        "assignment_group_id": 4, "assigned_to": 3, "escalation": False,
        "product_id": 128, "installed_product_id": 3,
    }))["case_id"]

    case_b = (await call("create_new_case", {
        "account_id": 1, "contact_id": 123, "channel": "web", "priority": "moderate",
        "state": "new", "short_description": "M1 replay case B",
        "assignment_group_id": 4, "assigned_to": 5, "escalation": False,
        "product_id": 128, "installed_product_id": 3,
    }))["case_id"]

    await call("update_case", {
        "case_id": case_a, "state": "in_progress", "priority": "critical",
        "escalation": True, "escalation_reason": "customer_request",
    })
    await call("update_case", {"case_id": case_b, "state": "pending"})

    await call("assign_case_to_user", {"case_id": case_a, "assigned_to_user_id": 6})
    await call("assign_case_to_user", {"case_id": case_b, "assigned_to_user_id": 9})

    sla_a = (await call("link_new_case_sla", {"case_id": case_a, "sla_def_id": 1, "stage": "in_progress"}))["case_sla_id"]
    sla_b = (await call("link_new_case_sla", {"case_id": case_b, "sla_def_id": 2, "stage": "in_progress"}))["case_sla_id"]

    notif_a = await call("send_notification", {"case_id": case_a, "email": "replay-audit@example.com", "type": "update"})

    await call("update_case_sla_details", {"case_sla_id": sla_a, "stage": "completed", "has_breached": False})

    captured_ids = {
        "case_a": case_a,
        "case_b": case_b,
        "sla_link_a": sla_a,
        "sla_link_b": sla_b,
        "notification_a": notif_a.get("notification_id") if isinstance(notif_a, dict) else None,
    }
    return {"call_log": log, "captured_ids": captured_ids}


async def main():
    t0 = time.time()
    replicas = {}
    for label in ("R1", "R2", "R3"):
        db_id = gc.seed(gc.CSM_URL, gc.CSM_SEED)
        print(f"{label}: seeded {db_id}")
        seq_result = await run_sequence(gc.CSM_URL, db_id)
        print(f"{label}: sequence complete, captured_ids={seq_result['captured_ids']}")
        replicas[label] = {"db_id": db_id, **seq_result}

    # captured new-row PK comparison
    id_fields = ["case_a", "case_b", "sla_link_a", "sla_link_b", "notification_a"]
    ids_by_field = {f: {label: replicas[label]["captured_ids"][f] for label in replicas} for f in id_fields}
    ids_identical = {f: len(set(v.values())) == 1 for f, v in ids_by_field.items()}
    print("\nNew-row primary key identity across replays:")
    for f in id_fields:
        print(f"  {f}: {ids_by_field[f]} -> identical={ids_identical[f]}")

    # full table dumps, natural (unsorted) order, per replica
    dumps = {}
    for label in replicas:
        dumps[label] = dd.dump_all_tables(gc.CSM_URL, replicas[label]["db_id"])
        print(f"{label}: dumped {len(dumps[label])} tables, {dd.total_rows(dumps[label])} rows")

    diff_report = dd.positional_diff_multi(dumps)
    varying = dd.varying_columns_summary_multi(diff_report["cell_diffs"])

    print(f"\nrow_count_mismatch: {diff_report['row_count_mismatch']}")
    print(f"tables_not_common_to_all: {diff_report['tables_not_common_to_all']}")
    print(f"Varying table.column keys ({len(varying)}):")
    for key, v in sorted(varying.items()):
        print(f"  {key}: behavior={v['behavior']}, diff_count={v['diff_count']}")

    # also verify canonical hash equality modulo the varying columns: build a
    # "cleaned" dump with volatile columns stripped, then hash-compare.
    volatile_cols_by_table = {}
    for v in varying.values():
        volatile_cols_by_table.setdefault(v["table"], set()).add(v["column"])

    def strip_volatile(dump):
        out = {}
        for table, rows in dump.items():
            drop = volatile_cols_by_table.get(table, set())
            out[table] = [{k: v for k, v in row.items() if k not in drop} for row in rows]
        return out

    hashes_stripped = {}
    for label in dumps:
        canon = dd.canonicalize_dump(strip_volatile(dumps[label]))
        hashes_stripped[label] = dd.hash_canonical(canon)["overall"]
    identical_modulo_volatile = len(set(hashes_stripped.values())) == 1
    print(f"\nIdentical modulo volatile columns (hash after stripping {sum(len(v) for v in volatile_cols_by_table.values())} volatile columns): {identical_modulo_volatile}")
    print(f"  stripped hashes: {hashes_stripped}")

    overall_identical_raw = len({dd.hash_canonical(dd.canonicalize_dump(dumps[l]))["overall"] for l in dumps}) == 1

    # write data/eog/volatile-columns-csm.json
    volatile_out = {
        "domain": "csm",
        "replicas": {label: replicas[label]["db_id"] for label in replicas},
        "sequence_length": len(replicas["R1"]["call_log"]),
        "distinct_tools_used": sorted({c["tool"] for c in replicas["R1"]["call_log"]}),
        "raw_identical": overall_identical_raw,
        "identical_modulo_volatile_columns": identical_modulo_volatile,
        "new_row_pk_identical_across_replays": ids_identical,
        "captured_new_row_ids": ids_by_field,
        "volatile_columns": varying,
        "row_count_mismatch": diff_report["row_count_mismatch"],
        "tables_not_common_to_all": diff_report["tables_not_common_to_all"],
    }
    with open(f"{DATA_DIR}/volatile-columns-csm.json", "w") as f:
        json.dump(volatile_out, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote -> {DATA_DIR}/volatile-columns-csm.json")

    # full evidence (call logs + diff) for the audit doc
    evidence = {
        "replicas": replicas,
        "ids_identical": ids_identical,
        "diff_report": diff_report,
        "varying_columns": varying,
        "identical_modulo_volatile_columns": identical_modulo_volatile,
        "raw_identical": overall_identical_raw,
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(f"{EVIDENCE_DIR}/test3_replay_csm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"Wrote full evidence -> {EVIDENCE_DIR}/test3_replay_csm.json")

    for label in replicas:
        gc.delete_db(gc.CSM_URL, replicas[label]["db_id"])
    print(f"\ncleaned up 3 replica dbs. Total wall time: {time.time() - t0:.2f}s")

    if overall_identical_raw:
        verdict = "PASS (byte-identical)"
    elif identical_modulo_volatile:
        verdict = "PASS modulo volatile columns (see volatile-columns-csm.json)"
    else:
        verdict = "FAIL (differs beyond known volatile columns)"
    print("\nVERDICT:", verdict)


if __name__ == "__main__":
    asyncio.run(main())
