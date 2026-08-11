"""
M4 TEST A, MUTATING DETERMINISM (itsm)

Same machinery as test_a_mutating_determinism_csm.py (reuses m1_audit's
gym_client/db_diff), extended to cover EVERY mutating tool in the itsm union
(data/eog/tool-union-itsm.json): add_child_incident, delete_incident_slas,
map_change_request, remove_child_incident, send_notification, update_change,
update_configuration_item, update_incident (8 distinct tools).

Per M1's finding, itsm's tools/call requires NO x-user-email/context header
(create_incident succeeded with zero context) -- confirmed still true here.

All pre-existing-entity arguments hardcoded from probe_seed_entities.py
(incident_id INC_001/INC_002/INC_003/INC_005/INC_008 all org ORG_001,
change_id CHG_001/CHG_002 both org ORG_001, configuration_item_id CI_001,
incident_sla_id TSLA_001). add_child_incident uses a fresh (parent, child)
pair -- (INC_003, INC_008) -- verified absent from the seed's existing
child_incident rows and not violating the ck_child_inc_not_self /
uq_parent_child_incident constraints (both org ORG_001). Its captured
child_incident_mapping_id is fed into remove_child_incident within the SAME
replica, so the remove targets exactly the row just created (deterministic,
isolated). send_notification recipient is carlos.rodriguez@techcorp.com
(USER_003) -- deliberately NOT marcus.thompson@techcorp.com (USER_001), since
Test D characterizes that self-recipient no-op separately; this call is meant
to actually create a notification row.

Ran on 3 independently-seeded databases (gc.ITSM_SEED, confirmed identical to
every itsm task.json's seed_database_file).

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/test_a_mutating_determinism_itsm.py
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

MUTATING_UNION = json.load(open(f"{DATA_DIR}/tool-union-itsm.json"))["mutating_tools"]


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
    client = await gc.new_client(base_url, database_id=db_id)  # no x-user-email needed for itsm (M1 finding)
    log = []
    tools_called = []

    async def call(tool, args):
        res = await client.call_tool(tool, args, database_id=db_id)
        ok, parsed = extract_result(res)
        log.append({"step": len(log) + 1, "tool": tool, "arguments": args, "ok": ok, "parsed_result": parsed})
        tools_called.append(tool)
        if not ok:
            raise RuntimeError(f"tool call failed at step {len(log)}: {tool} args={args} -> {parsed}")
        return parsed

    # 1. update_incident on pre-existing INC_002
    await call("update_incident", {
        "incident_id": "INC_002", "status": "on_hold", "on_hold_reason": "Awaiting Change",
        "priority": "critical", "worknotes": "M4 reaudit worknote",
    })

    # 2. update_change on pre-existing CHG_001
    await call("update_change", {
        "change_id": "CHG_001", "status": "implement", "priority": "high",
        "close_notes": "M4 reaudit close note",
    })

    # 3. update_configuration_item on pre-existing CI_001 -- money-relevant column (cost)
    await call("update_configuration_item", {"configuration_item_id": "CI_001", "cost": 1250.75, "status": "maintenance"})

    # 4. add_child_incident -- fresh (parent, child) pair, not in seed's existing child_incident rows
    new_child_mapping = (await call("add_child_incident", {
        "parent_incident": "INC_003", "child_incident": "INC_008",
    }))["child_incident_mapping_id"]

    # 5. remove_child_incident -- targets EXACTLY the row created in step 4 (dynamically captured)
    await call("remove_child_incident", {"child_incident_mapping_id": new_child_mapping})

    # 6. map_change_request -- new change_request_mapping row; both entities org ORG_001,
    #    INC_005 not already mapped to CHG_002 (verified against seed)
    new_crm = (await call("map_change_request", {"change_id": "CHG_002", "incident_id": "INC_005"}))["change_request_mapping_id"]

    # 7. send_notification -- non-self recipient (carlos.rodriguez, USER_003), should create a row
    #    (the USER_001 self-recipient no-op quirk is characterized separately in Test D)
    new_notification = (await call("send_notification", {
        "incident_id": "INC_001", "email": "carlos.rodriguez@techcorp.com", "type": "update",
        "status": "sent", "subject": "M4 reaudit notification", "message": "Determinism reaudit test message",
    })).get("notification_id")

    # 8. delete_incident_slas -- narrow single-row filter, unrelated to anything else touched above
    await call("delete_incident_slas", {"incident_sla_id": "TSLA_001"})

    assert set(tools_called) == set(MUTATING_UNION), (
        f"sequence did not exercise every mutating tool in the union! "
        f"missing={set(MUTATING_UNION) - set(tools_called)} extra={set(tools_called) - set(MUTATING_UNION)}"
    )

    captured_ids = {
        "new_child_mapping": new_child_mapping, "new_change_request_mapping": new_crm,
        "new_notification": new_notification,
    }
    return {"call_log": log, "captured_ids": captured_ids, "tools_called": tools_called}


async def main():
    t0 = time.time()
    replicas = {}
    try:
        for label in ("R1", "R2", "R3"):
            db_id = gc.seed(gc.ITSM_URL, gc.ITSM_SEED)
            print(f"{label}: seeded {db_id}")
            seq_result = await run_sequence(gc.ITSM_URL, db_id)
            print(f"{label}: sequence complete ({len(seq_result['tools_called'])} calls, "
                  f"{len(set(seq_result['tools_called']))} distinct tools), captured_ids={seq_result['captured_ids']}")
            replicas[label] = {"db_id": db_id, **seq_result}
    except Exception:
        for r in replicas.values():
            gc.delete_db(gc.ITSM_URL, r["db_id"])
        raise

    id_fields = list(replicas["R1"]["captured_ids"].keys())
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
    print(f"\nIdentical modulo volatile columns (stripping {sum(len(v) for v in volatile_cols_by_table.values())} columns): {identical_modulo_volatile}")
    print(f"  stripped hashes: {hashes_stripped}")

    overall_identical_raw = len({dd.hash_canonical(dd.canonicalize_dump(dumps[l]))["overall"] for l in dumps}) == 1
    non_timestamp_varying = {k: v for k, v in varying.items() if v["behavior"] != "wall-clock timestamp"}

    evidence = {
        "test": "A_mutating_determinism_itsm",
        "mutating_union": MUTATING_UNION,
        "mutating_union_count": len(MUTATING_UNION),
        "tools_exercised": sorted(set(replicas["R1"]["tools_called"])),
        "tools_exercised_count": len(set(replicas["R1"]["tools_called"])),
        "coverage_complete": set(replicas["R1"]["tools_called"]) == set(MUTATING_UNION),
        "replicas": {label: replicas[label]["db_id"] for label in replicas},
        "call_logs": {label: replicas[label]["call_log"] for label in replicas},
        "captured_new_row_ids": ids_by_field,
        "new_row_pk_identical_across_replays": ids_identical,
        "diff_report": diff_report,
        "varying_columns": varying,
        "non_timestamp_varying_columns": non_timestamp_varying,
        "identical_modulo_volatile_columns": identical_modulo_volatile,
        "raw_identical": overall_identical_raw,
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(f"{EVIDENCE_DIR}/test_a_itsm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote full evidence -> {EVIDENCE_DIR}/test_a_itsm.json")

    for label in replicas:
        gc.delete_db(gc.ITSM_URL, replicas[label]["db_id"])
    print(f"\ncleaned up 3 replica dbs. Total wall time: {time.time() - t0:.2f}s")

    if overall_identical_raw:
        verdict = "PASS (byte-identical)"
    elif identical_modulo_volatile:
        verdict = "PASS modulo volatile columns"
    elif not non_timestamp_varying:
        verdict = "PASS modulo volatile columns (all varying columns classified as wall-clock timestamps)"
    else:
        verdict = f"FAIL/INVESTIGATE -- non-timestamp variance in: {sorted(non_timestamp_varying.keys())}"
    print("\nVERDICT:", verdict)
    print("all_ids_identical:", all(ids_identical.values()))


if __name__ == "__main__":
    asyncio.run(main())
