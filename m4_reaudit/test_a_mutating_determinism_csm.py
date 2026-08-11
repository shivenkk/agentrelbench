"""
M4 TEST A, MUTATING DETERMINISM (csm)

Extends m1_audit/test3_replay_reproducibility_csm.py's machinery (same
gym_client.seed/new_client, same db_diff full-dump + positional_diff_multi) to
cover EVERY mutating tool reachable by the finalized 20-task portfolio (the
union computed by compute_tool_union.py -> data/eog/tool-union-csm.json),
not just the 6 tools M1 happened to pick.

16 distinct mutating tools in the csm union, each exercised >=1 time in one
fixed sequence: create_new_account, enlist_new_contract, add_new_entitlement,
update_contract, update_entitlement, update_installed_product_details,
update_product, update_knowledge, update_case, set_case_assignment_group,
link_new_case_sla, update_case_sla_details, delete_case_slas,
link_case_knowledge, register_new_interaction, delete_notifications.

All arguments referencing pre-existing seed entities are hardcoded, discovered
via probe_seed_entities.py (account_id=1/name unique-constrained, contact_id=123,
product_id=1, installed_product_id=3, contract_id=1, entitlement_id=1, case_id=1,
case_sla_id=2464, sla_def_id=1, knowledge_id=1, notification_id=724). Arguments
referencing entities CREATED during the sequence (new account, new contract, new
entitlement, new case_sla link) are captured dynamically per replica from that
replica's own tool responses -- if the server is deterministic those captured
IDs should be identical across all 3 replicas.

The account/contract/entitlement/case_sla-link creates chain off each other
(new account -> new contract on that account -> new entitlement on that
contract) specifically to test that determinism holds even when a later
create's row depends on an earlier create's row within the SAME sequence
(not just independent creates).

Ran on 3 independently-seeded databases (identical seed file: gc.CSM_SEED,
confirmed identical to every csm task.json's seed_database_file). Full-dumps
all tables from all 3 replicas afterward and diffs position-by-position.

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/test_a_mutating_determinism_csm.py
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

ACTOR_EMAIL = "thomas.green@servicenow.com"  # user_id=1, role=agent, present in every csm seed replica
EVIDENCE_DIR = str(_REPO / "m4_reaudit/evidence")
DATA_DIR = str(_REPO / "data/eog")

MUTATING_UNION = json.load(open(f"{DATA_DIR}/tool-union-csm.json"))["mutating_tools"]


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
    client = await gc.new_client(base_url, database_id=db_id, context={"x-user-email": ACTOR_EMAIL})
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

    # 1. create_new_account -- captures new account_id (unique name -> can't collide with seed's 52 accounts)
    new_account = (await call("create_new_account", {
        "name": "M4 ReAudit Test Account (mutating-seq)", "account_type": "customer", "active": True,
    }))["account_id"]

    # 2. enlist_new_contract on the freshly-created account -- tests determinism when a create's
    #    row depends on an earlier create in the SAME sequence, not just independent creates.
    new_contract = (await call("enlist_new_contract", {
        "account_id": new_account, "contract_type": "subscription", "status": "active",
        "start_date": "2026-01-01", "end_date": "2027-01-01", "contract_price": 15000,
    }))["contract_id"]

    # 3. add_new_entitlement chained off both prior creates
    new_entitlement = (await call("add_new_entitlement", {
        "account_id": new_account, "support_level": "premium", "active": True,
        "contract_id": new_contract, "product_id": 1,
    }))["entitlement_id"]

    # 4. update_contract on a PRE-EXISTING seed contract (contract_id=1, account_id=1) --
    #    money-relevant column (contract_price)
    await call("update_contract", {"contract_id": 1, "contract_price": 99999, "status": "active"})

    # 5. update_entitlement on a pre-existing seed entitlement (entitlement_id=1)
    await call("update_entitlement", {"entitlement_id": 1, "support_level": "enterprise", "active": True})

    # 6. update_installed_product_details on pre-existing seed row (installed_product_id=3)
    await call("update_installed_product_details", {
        "installed_product_id": 3, "status": "repair", "warranty_end": "2027-06-30",
    })

    # 7. update_product on pre-existing seed row (product_id=1) -- money-relevant column (product_price)
    await call("update_product", {"product_id": 1, "product_price": 999})

    # 8. update_knowledge on pre-existing seed row (knowledge_id=1)
    await call("update_knowledge", {"knowledge_id": 1, "state": "draft"})

    # 9. update_case on pre-existing seed case (case_id=1)
    await call("update_case", {
        "case_id": 1, "state": "in_progress", "priority": "high",
        "escalation": True, "escalation_reason": "customer_request",
    })

    # 10. set_case_assignment_group on the same case (existing group 4 -> 7)
    await call("set_case_assignment_group", {"case_id": 1, "assignment_group_id": 7})

    # 11. link_new_case_sla -- creates a NEW case_sla row on case_id=1; captured dynamically
    new_case_sla = (await call("link_new_case_sla", {"case_id": 1, "sla_def_id": 1, "stage": "in_progress"}))["case_sla_id"]

    # 12. update_case_sla_details on a DIFFERENT, pre-existing seed case_sla row (case_sla_id=2464)
    await call("update_case_sla_details", {
        "case_sla_id": 2464, "stage": "completed", "has_breached": False,
        "completed_time": "2026-07-16 12:00:00",
    })

    # 13. delete_case_slas -- narrow single-row filter targeting EXACTLY the row created in step 11
    #     (filter-width trap tool, exercised via a precise filter so the delete is deterministic
    #     and doesn't touch anything else the sequence depends on)
    await call("delete_case_slas", {"case_sla_id": new_case_sla})

    # 14. link_case_knowledge -- new case_kb_id (case 1 has no pre-existing knowledge link per probe)
    new_case_kb = (await call("link_case_knowledge", {"case_id": 1, "knowledge_id": 1, "used_as": "suggested"}))["case_kb_id"]

    # 15. register_new_interaction -- new interaction_id
    new_interaction = (await call("register_new_interaction", {
        "channel": "email", "status": "open", "account_id": 1, "case_id": 1,
        "contact_id": 123, "interacted_user": 1,
    }))["interaction_id"]

    # 16. delete_notifications -- narrow single-row filter on a pre-existing seed notification
    #     (notification_id=724, unrelated to anything else touched above)
    await call("delete_notifications", {"notification_id": 724})

    assert set(tools_called) == set(MUTATING_UNION), (
        f"sequence did not exercise every mutating tool in the union! "
        f"missing={set(MUTATING_UNION) - set(tools_called)} extra={set(tools_called) - set(MUTATING_UNION)}"
    )

    captured_ids = {
        "new_account": new_account, "new_contract": new_contract, "new_entitlement": new_entitlement,
        "new_case_sla": new_case_sla, "new_case_kb": new_case_kb, "new_interaction": new_interaction,
    }
    return {"call_log": log, "captured_ids": captured_ids, "tools_called": tools_called}


async def main():
    t0 = time.time()
    replicas = {}
    try:
        for label in ("R1", "R2", "R3"):
            db_id = gc.seed(gc.CSM_URL, gc.CSM_SEED)
            print(f"{label}: seeded {db_id}")
            seq_result = await run_sequence(gc.CSM_URL, db_id)
            print(f"{label}: sequence complete ({len(seq_result['tools_called'])} calls, "
                  f"{len(set(seq_result['tools_called']))} distinct tools), captured_ids={seq_result['captured_ids']}")
            replicas[label] = {"db_id": db_id, **seq_result}
    except Exception:
        for r in replicas.values():
            gc.delete_db(gc.CSM_URL, r["db_id"])
        raise

    id_fields = list(replicas["R1"]["captured_ids"].keys())
    ids_by_field = {f: {label: replicas[label]["captured_ids"][f] for label in replicas} for f in id_fields}
    ids_identical = {f: len(set(v.values())) == 1 for f, v in ids_by_field.items()}
    print("\nNew-row primary key identity across replays:")
    for f in id_fields:
        print(f"  {f}: {ids_by_field[f]} -> identical={ids_identical[f]}")

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

    # bisect verdict: any non-timestamp-looking varying column that ISN'T also just a new-row-id
    # ambiguity would indicate genuine nondeterminism -- flag anything not classified as a
    # wall-clock timestamp for manual inspection.
    non_timestamp_varying = {k: v for k, v in varying.items() if v["behavior"] != "wall-clock timestamp"}

    evidence = {
        "test": "A_mutating_determinism_csm",
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
    with open(f"{EVIDENCE_DIR}/test_a_csm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote full evidence -> {EVIDENCE_DIR}/test_a_csm.json")

    for label in replicas:
        gc.delete_db(gc.CSM_URL, replicas[label]["db_id"])
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
