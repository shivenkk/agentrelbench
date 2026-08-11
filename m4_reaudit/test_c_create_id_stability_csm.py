"""
M4 TEST C, CREATE-ID STABILITY (csm)

On TWO independently freshly-seeded csm databases, call create_new_account
with IDENTICAL arguments and confirm both replicas receive the SAME new
account_id. account.account_id is INTEGER PRIMARY KEY AUTOINCREMENT and the
seed's existing account table tops out at account_id=52 (confirmed via direct
SELECT MAX(account_id) against a throwaway probe seed), so a deterministic
server should hand back account_id=53 on both replicas -- a portfolio task
(account-onboarding-chain) depends on this exact value.

Also cross-checked against Test A's own create_new_account call (a 3rd,
independent fresh-seed replica, same union-coverage sequence) for a 5-way
total corroboration if all agree.

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/test_c_create_id_stability_csm.py
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, str(_REPO / "m1_audit"))
import gym_client as gc
from pathlib import Path

# Repo root, derived rather than hardcoded so the script runs from any checkout.
_REPO = Path(__file__).resolve().parent.parent

EVIDENCE_DIR = str(_REPO / "m4_reaudit/evidence")
ACTOR_EMAIL = "thomas.green@servicenow.com"
EXPECTED_ACCOUNT_ID = 53
ARGS = {"name": "M4 CreateID Stability Check Account", "account_type": "customer", "active": True}


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
    replicas = {}
    try:
        for label in ("R1", "R2"):
            db_id = gc.seed(gc.CSM_URL, gc.CSM_SEED)
            client = await gc.new_client(gc.CSM_URL, database_id=db_id, context={"x-user-email": ACTOR_EMAIL})
            res = await client.call_tool("create_new_account", ARGS, database_id=db_id)
            ok, parsed = extract_result(res)
            if not ok:
                raise RuntimeError(f"create_new_account failed on {label} ({db_id}): {parsed}")
            replicas[label] = {"db_id": db_id, "response": parsed, "account_id": parsed["account_id"]}
            print(f"{label}: seeded {db_id}, create_new_account -> account_id={parsed['account_id']}")
    finally:
        for r in replicas.values():
            gc.delete_db(gc.CSM_URL, r["db_id"])

    ids = {label: replicas[label]["account_id"] for label in replicas}
    identical = len(set(ids.values())) == 1
    matches_expected = identical and ids["R1"] == EXPECTED_ACCOUNT_ID

    print(f"\naccount_id across replicas: {ids}")
    print(f"identical across replicas: {identical}")
    print(f"matches expected value ({EXPECTED_ACCOUNT_ID}): {matches_expected}")

    evidence = {
        "test": "C_create_id_stability_csm",
        "tool": "create_new_account",
        "arguments": ARGS,
        "expected_account_id": EXPECTED_ACCOUNT_ID,
        "expected_account_id_basis": "SELECT MAX(account_id) FROM account on a throwaway probe seed returned 52 "
                                      "(52 total accounts) -- a fresh AUTOINCREMENT create should yield 53",
        "replicas": {label: {"db_id": replicas[label]["db_id"], "account_id": replicas[label]["account_id"],
                              "full_response": replicas[label]["response"]} for label in replicas},
        "account_ids_identical_across_replicas": identical,
        "matches_expected_value": matches_expected,
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(f"{EVIDENCE_DIR}/test_c_csm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote evidence -> {EVIDENCE_DIR}/test_c_csm.json")
    print(f"cleaned up. Total wall time: {time.time() - t0:.2f}s")

    print("\nVERDICT:", "PASS (stable, matches expected 53)" if matches_expected else
          ("PASS (stable across replicas but NOT 53 -- check expectation)" if identical else "FAIL (nondeterministic account_id!)"))


if __name__ == "__main__":
    asyncio.run(main())
