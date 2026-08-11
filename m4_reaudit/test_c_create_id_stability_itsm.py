"""
M4 TEST C, CREATE-ID STABILITY (itsm)

On TWO independently freshly-seeded itsm databases, call create_incident with
IDENTICAL arguments and confirm both replicas receive the SAME new
incident_id. The seed has 23 existing incidents (confirmed via COUNT(*)
against a throwaway probe seed, highest = INC_023), so a deterministic server
should hand back INC_024 on both -- matching M1's own test3_replay_itsm.py
finding (incident_a=INC_024 when creating on this identical seed file back
then), a useful cross-time corroboration that nothing has drifted.

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/test_c_create_id_stability_itsm.py
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
EXPECTED_INCIDENT_ID = "INC_024"
ARGS = {
    "caller_id": "USER_005", "short_description": "M4 CreateID Stability Check",
    "category": "software", "priority": "high",
}


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
            db_id = gc.seed(gc.ITSM_URL, gc.ITSM_SEED)
            client = await gc.new_client(gc.ITSM_URL, database_id=db_id)  # no context needed, per M1
            res = await client.call_tool("create_incident", ARGS, database_id=db_id)
            ok, parsed = extract_result(res)
            if not ok:
                raise RuntimeError(f"create_incident failed on {label} ({db_id}): {parsed}")
            replicas[label] = {"db_id": db_id, "response": parsed, "incident_id": parsed["incident_id"]}
            print(f"{label}: seeded {db_id}, create_incident -> incident_id={parsed['incident_id']}")
    finally:
        for r in replicas.values():
            gc.delete_db(gc.ITSM_URL, r["db_id"])

    ids = {label: replicas[label]["incident_id"] for label in replicas}
    identical = len(set(ids.values())) == 1
    matches_expected = identical and ids["R1"] == EXPECTED_INCIDENT_ID

    print(f"\nincident_id across replicas: {ids}")
    print(f"identical across replicas: {identical}")
    print(f"matches expected value ({EXPECTED_INCIDENT_ID}): {matches_expected}")

    evidence = {
        "test": "C_create_id_stability_itsm",
        "tool": "create_incident",
        "arguments": ARGS,
        "expected_incident_id": EXPECTED_INCIDENT_ID,
        "expected_incident_id_basis": "SELECT COUNT(*) FROM incident on a throwaway probe seed returned 23 "
                                       "(highest = INC_023) -- a fresh create should yield INC_024; matches M1's "
                                       "own test3_replay_reproducibility_itsm.py finding on this identical seed file",
        "replicas": {label: {"db_id": replicas[label]["db_id"], "incident_id": replicas[label]["incident_id"],
                              "full_response": replicas[label]["response"]} for label in replicas},
        "incident_ids_identical_across_replicas": identical,
        "matches_expected_value": matches_expected,
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(f"{EVIDENCE_DIR}/test_c_itsm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote evidence -> {EVIDENCE_DIR}/test_c_itsm.json")
    print(f"cleaned up. Total wall time: {time.time() - t0:.2f}s")

    print("\nVERDICT:", "PASS (stable, matches expected INC_024)" if matches_expected else
          ("PASS (stable across replicas but NOT INC_024 -- check expectation)" if identical else "FAIL (nondeterministic incident_id!)"))


if __name__ == "__main__":
    asyncio.run(main())
