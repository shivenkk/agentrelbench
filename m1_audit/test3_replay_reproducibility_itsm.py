"""
TEST 3b — REPLAY REPRODUCIBILITY (itsm, lighter version: one seeding pair, 6 calls)

Seed 2 independent itsm databases from the identical seed file, execute an
identical fixed sequence of 6 tool calls (5 distinct state-changing tools:
create_incident, update_incident, register_configuration_item,
update_configuration_item, send_notification) against each, dump every table,
diff position-by-position. Unlike csm, itsm's tools/call does NOT require an
x-user-email context header (confirmed empirically via probe_itsm_call_shape.py
-- create_incident succeeded with no context at all). IDs in itsm are
formatted strings (INC_NNN, CI_NNN) rather than csm's plain integers.

Rerun: /path/to/.venv/bin/python m1_audit/test3_replay_reproducibility_itsm.py
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/Users/shiven/Documents/Projects/agentrelbench/m1_audit")
import gym_client as gc
import db_diff as dd

DATA_DIR = "/Users/shiven/Documents/Projects/agentrelbench/data/eog"
EVIDENCE_DIR = "/Users/shiven/Documents/Projects/agentrelbench/m1_audit/evidence"


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


async def run_sequence(base_url: str, db_id: str) -> dict:
    client = await gc.new_client(base_url, database_id=db_id)  # no x-user-email needed for itsm
    log = []

    async def call(tool, args):
        res = await client.call_tool(tool, args, database_id=db_id)
        ok, parsed = extract_result(res)
        log.append({"step": len(log) + 1, "tool": tool, "arguments": args, "ok": ok, "parsed_result": parsed})
        if not ok:
            raise RuntimeError(f"tool call failed at step {len(log)}: {tool} args={args} -> {parsed}")
        return parsed

    incident_a = (await call("create_incident", {
        "caller_id": "USER_005", "short_description": "M1 replay incident A",
        "category": "software", "priority": "high", "impact": "medium",
        "urgency": "medium", "assigned_to": "USER_003", "assignment_group": "GROUP_001",
        "channel": "email",
    }))["incident_id"]

    incident_b = (await call("create_incident", {
        "caller_id": "USER_002", "short_description": "M1 replay incident B",
        "category": "hardware", "priority": "moderate",
    }))["incident_id"]

    await call("update_incident", {
        "incident_id": incident_a, "status": "in_progress", "priority": "critical",
        "worknotes": "M1 audit replay update",
    })

    ci_a = (await call("register_configuration_item", {
        "name": "M1 Audit CI", "owner_id": "USER_003", "location_id": "LOC_001",
        "serial_number": "M1AUDIT-SN-0001", "status": "in_use", "cost": 999.99,
    }))["configuration_item_id"]

    await call("update_configuration_item", {
        "configuration_item_id": ci_a, "cost": 1099.5, "status": "maintenance",
    })

    await call("send_notification", {
        # must be an email that exists in the seed's users table (validated
        # server-side: USER_EMAIL_NOT_FOUND otherwise) -- USER_003 / Carlos Rodriguez
        "incident_id": incident_a, "email": "carlos.rodriguez@techcorp.com", "type": "update",
        "subject": "Audit Update", "message": "test message", "status": "queued",
    })

    captured_ids = {"incident_a": incident_a, "incident_b": incident_b, "ci_a": ci_a}
    return {"call_log": log, "captured_ids": captured_ids}


async def main():
    t0 = time.time()
    replicas = {}
    try:
        for label in ("R1", "R2"):
            db_id = gc.seed(gc.ITSM_URL, gc.ITSM_SEED)
            print(f"{label}: seeded {db_id}")
            seq_result = await run_sequence(gc.ITSM_URL, db_id)
            print(f"{label}: sequence complete, captured_ids={seq_result['captured_ids']}")
            replicas[label] = {"db_id": db_id, **seq_result}
    except Exception:
        for r in replicas.values():
            gc.delete_db(gc.ITSM_URL, r["db_id"])
        raise

    id_fields = ["incident_a", "incident_b", "ci_a"]
    ids_by_field = {f: {label: replicas[label]["captured_ids"][f] for label in replicas} for f in id_fields}
    ids_identical = {f: len(set(v.values())) == 1 for f, v in ids_by_field.items()}
    print("\nNew-row primary key identity across replays:")
    for f in id_fields:
        print(f"  {f}: {ids_by_field[f]} -> identical={ids_identical[f]}")

    dumps = {}
    for label in replicas:
        dumps[label] = dd.dump_all_tables(gc.ITSM_URL, replicas[label]["db_id"])
        print(f"{label}: dumped {len(dumps[label])} tables, {dd.total_rows(dumps[label])} rows")

    diff_report = dd.positional_diff_multi(dumps)
    varying = dd.varying_columns_summary_multi(diff_report["cell_diffs"])

    print(f"\nrow_count_mismatch: {diff_report['row_count_mismatch']}")
    print(f"tables_not_common_to_all: {diff_report['tables_not_common_to_all']}")
    print(f"Varying table.column keys ({len(varying)}):")
    for key, v in sorted(varying.items()):
        print(f"  {key}: behavior={v['behavior']}, diff_count={v['diff_count']}")

    volatile_cols_by_table = {}
    for v in varying.values():
        volatile_cols_by_table.setdefault(v["table"], set()).add(v["column"])

    def strip_volatile(dump):
        return {
            table: [{k: v for k, v in row.items() if k not in volatile_cols_by_table.get(table, set())} for row in rows]
            for table, rows in dump.items()
        }

    hashes_stripped = {label: dd.hash_canonical(dd.canonicalize_dump(strip_volatile(dumps[label])))["overall"] for label in dumps}
    identical_modulo_volatile = len(set(hashes_stripped.values())) == 1
    print(f"\nIdentical modulo volatile columns: {identical_modulo_volatile}")
    print(f"  stripped hashes: {hashes_stripped}")

    overall_identical_raw = len({dd.hash_canonical(dd.canonicalize_dump(dumps[l]))["overall"] for l in dumps}) == 1

    volatile_out = {
        "domain": "itsm",
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
    with open(f"{DATA_DIR}/volatile-columns-itsm.json", "w") as f:
        json.dump(volatile_out, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote -> {DATA_DIR}/volatile-columns-itsm.json")

    evidence = {
        "replicas": replicas,
        "ids_identical": ids_identical,
        "diff_report": diff_report,
        "varying_columns": varying,
        "identical_modulo_volatile_columns": identical_modulo_volatile,
        "raw_identical": overall_identical_raw,
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(f"{EVIDENCE_DIR}/test3_replay_itsm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"Wrote full evidence -> {EVIDENCE_DIR}/test3_replay_itsm.json")

    for label in replicas:
        gc.delete_db(gc.ITSM_URL, replicas[label]["db_id"])
    print(f"\ncleaned up replica dbs. Total wall time: {time.time() - t0:.2f}s")

    if overall_identical_raw:
        verdict = "PASS (byte-identical)"
    elif identical_modulo_volatile:
        verdict = "PASS modulo volatile columns (see volatile-columns-itsm.json)"
    else:
        verdict = "FAIL (differs beyond known volatile columns)"
    print("\nVERDICT:", verdict)


if __name__ == "__main__":
    asyncio.run(main())
