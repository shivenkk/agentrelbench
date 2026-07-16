"""
M4 TEST D — itsm send_notification SELF-RECIPIENT NO-OP QUIRK (characterize, don't fix)

tasks/itsm/notification-outward/RATIONALE.md already documents, from prior task
design work: "send_notification returns success but creates no row when the
recipient is USER_001 (the default acting user, marcus.thompson) -- a
self-notification guard keyed on that one user. A different admin (USER_007)
DOES receive a row, so it is USER_001-specific, not admin-wide." This script
re-derives that finding from scratch with live evidence (row counts + full
tool responses before/after, on fresh seeds) and additionally probes WHETHER
the guard is (a) hardcoded server-side to marcus.thompson's email specifically,
or (b) a generic "recipient == request's acting-user context" mechanism that
would follow an explicit x-user-email header to a DIFFERENT user -- itsm's
tools/call famously requires no auth context at all (M1 finding), so "the
acting user" has no session meaning unless the server reads an optional
x-user-email header nobody is required to send.

Five calls per replica, on two independently-seeded fresh DBs (2-way
reproducibility, mirroring Test C):
  A. send_notification(INC_001, marcus.thompson@techcorp.com), NO context header
     -> expect: tool reports success, but NO row appears (the documented no-op).
  B. send_notification(INC_001, carlos.rodriguez@techcorp.com), NO context header
     -> expect: a new row appears (control: non-self recipient works normally).
  C. send_notification(INC_002, marcus.thompson@techcorp.com), NO context header
     -> expect: also no-ops (rules out INC_001-specific coincidence).
  D. send_notification(INC_002, carlos.rodriguez@techcorp.com),
     WITH context={"x-user-email": "carlos.rodriguez@techcorp.com"} (recipient
     matches an EXPLICIT alternate "acting user" header)
     -> if this ALSO no-ops: the guard is context-driven (keyed on whatever
        x-user-email is asserted, defaulting to nobody since none is required).
     -> if this creates a row normally: the guard is hardcoded to
        marcus.thompson/USER_001 specifically, regardless of any header.
  E. send_notification(INC_002, benjamin.chen@techcorp.com),
     WITH context={"x-user-email": "marcus.thompson@techcorp.com"} (a USER_001
     header is present, but the recipient is a THIRD party, not USER_001)
     -> control: confirms merely SENDING a marcus.thompson context header
        doesn't itself suppress notifications to other people.

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/test_d_notification_quirk_itsm.py
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/Users/shiven/Documents/Projects/agentrelbench/m1_audit")
import gym_client as gc
import db_diff as dd

EVIDENCE_DIR = "/Users/shiven/Documents/Projects/agentrelbench/m4_reaudit/evidence"
MARCUS = "marcus.thompson@techcorp.com"   # USER_001, itsm's documented default acting user
CARLOS = "carlos.rodriguez@techcorp.com"  # USER_003
BENJAMIN = "benjamin.chen@techcorp.com"   # USER_005


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


def count_notifications(db_id, incident_id, email):
    r = gc.sql_runner(gc.ITSM_URL, f"SELECT COUNT(*) AS n FROM notification WHERE incident_id = '{incident_id}' AND email = '{email}';", db_id)
    return gc.rows_from_sql_result(r)[0]["n"]


async def run_replica(label):
    db_id = gc.seed(gc.ITSM_URL, gc.ITSM_SEED)
    client = await gc.new_client(gc.ITSM_URL, database_id=db_id)  # no context bound; overridden per-call below
    steps = []

    async def probe(name, incident_id, email, context=None, **extra_args):
        before = count_notifications(db_id, incident_id, email)
        args = {"incident_id": incident_id, "email": email, "type": "update", "status": "sent",
                "subject": f"quirk-test-{name}", "message": f"M4 Test D probe {name}", **extra_args}
        res = await client.call_tool("send_notification", args, database_id=db_id, context=context)
        ok, parsed = extract_result(res)
        after = count_notifications(db_id, incident_id, email)
        step = {
            "name": name, "incident_id": incident_id, "email": email, "context": context,
            "tool_call_ok": ok, "tool_reported_success": ok, "raw_response": parsed,
            "row_count_before": before, "row_count_after": after,
            "row_actually_created": after > before,
        }
        steps.append(step)
        return step

    a = await probe("A_marcus_no_context", "INC_001", MARCUS, context=None)
    b = await probe("B_carlos_no_context_control", "INC_001", CARLOS, context=None)
    c = await probe("C_marcus_second_incident", "INC_002", MARCUS, context=None)
    d = await probe("D_carlos_with_carlos_context", "INC_002", CARLOS, context={"x-user-email": CARLOS})
    e = await probe("E_benjamin_with_marcus_context_control", "INC_002", BENJAMIN, context={"x-user-email": MARCUS})

    gc.delete_db(gc.ITSM_URL, db_id)
    return {"db_id": db_id, "steps": steps}


async def main():
    t0 = time.time()
    replicas = {}
    for label in ("R1", "R2"):
        replicas[label] = await run_replica(label)
        print(f"{label} ({replicas[label]['db_id']}):")
        for s in replicas[label]["steps"]:
            print(f"  {s['name']}: tool_reported_success={s['tool_reported_success']}, "
                  f"row_actually_created={s['row_actually_created']} "
                  f"(before={s['row_count_before']}, after={s['row_count_after']})")

    # cross-replica consistency check: for each named step, is row_actually_created identical across R1/R2?
    step_names = [s["name"] for s in replicas["R1"]["steps"]]
    consistency = {}
    for name in step_names:
        vals = {label: next(s for s in replicas[label]["steps"] if s["name"] == name)["row_actually_created"] for label in replicas}
        consistency[name] = {"values": vals, "identical_across_replicas": len(set(vals.values())) == 1}

    print("\nCross-replica consistency (row_actually_created identical R1 vs R2):")
    for name, c in consistency.items():
        print(f"  {name}: {c['values']} -> identical={c['identical_across_replicas']}")

    a_r1 = next(s for s in replicas["R1"]["steps"] if s["name"] == "A_marcus_no_context")
    b_r1 = next(s for s in replicas["R1"]["steps"] if s["name"] == "B_carlos_no_context_control")
    c_r1 = next(s for s in replicas["R1"]["steps"] if s["name"] == "C_marcus_second_incident")
    d_r1 = next(s for s in replicas["R1"]["steps"] if s["name"] == "D_carlos_with_carlos_context")
    e_r1 = next(s for s in replicas["R1"]["steps"] if s["name"] == "E_benjamin_with_marcus_context_control")

    quirk_confirmed = (not a_r1["row_actually_created"]) and b_r1["row_actually_created"] and (not c_r1["row_actually_created"])
    mechanism = "UNKNOWN"
    if quirk_confirmed:
        if d_r1["row_actually_created"] and e_r1["row_actually_created"]:
            mechanism = ("HARDCODED to marcus.thompson@techcorp.com / USER_001 specifically -- an explicit "
                         "x-user-email header matching a DIFFERENT recipient (carlos) did NOT suppress that "
                         "send (step D created a row), so this is not a generic context-driven self-guard, "
                         "it is a special case for that one identity.")
        elif not d_r1["row_actually_created"]:
            mechanism = ("CONTEXT-DRIVEN -- recipient matching an explicit x-user-email header ALSO no-ops "
                         "(step D), even though the header identity (carlos) differs from the marcus-specific "
                         "case. Suggests a general 'recipient == asserted acting-user header' guard, with "
                         "marcus.thompson simply being what the itsm harness always asserts by convention "
                         "when tasks omit context, not a hardcoded literal.")

    # Two-layer correction to the existing "silently no-ops" characterization, established by
    # reading the vendored harness code (external/EnterpriseOps-Gym) alongside the live evidence
    # above -- NOT modified, only read, per the audit's rules.
    harness_layer_finding = {
        "summary": (
            "The MCP SERVER itself is NOT silent: it returns an explicit HTTP-level validation "
            "error (see raw_response for steps A/C above -- error_code=VALIDATION_ERROR, "
            "code=CANNOT_SEND_TO_SELF, message='Cannot send notification to yourself', with "
            "context.current_user_email='marcus.thompson@techcorp.com' and "
            "context.provided_value=<the email argument>). The apparent 'silence' is introduced "
            "one layer up, in the vendored benchmark harness's agent-facing orchestrators, which "
            "discard that error entirely before it ever reaches the LLM."
        ),
        "server_layer": (
            "benchmark/mcp_client.py MCPClient._send_request (lines ~209-227): when the tools/call "
            "HTTP POST returns a non-200 status (this validation error responds via FastAPI's "
            "standard {'detail': {...}} envelope, i.e. a 4xx, not a 200 OK MCP result with "
            "isError=true content), _send_request returns {'success': False, 'error': "
            "'MCP request failed: <status> - <body>'} -- note: NO 'result' key on this path."
        ),
        "harness_layer": (
            "orchestrators/react.py line 105 and orchestrators/planner_react.py line 277 both "
            "construct the agent-visible ToolMessage as "
            "`ToolMessage(content=json.dumps(tool_result.get('result', {})), ...)`. On the failure "
            "path above, tool_result has no 'result' key at all (only 'success': False and "
            "'error': <message>), so .get('result', {}) silently falls back to {} -- the LLM "
            "receives the literal string '{}' as the tool's return value, with the "
            "CANNOT_SEND_TO_SELF error code/message/context never surfaced. tool_result.get("
            "'success') is logged server-side (react.py line 89 / planner_react.py line 261) but "
            "never included in the message content."
        ),
        "practical_implication": (
            "From the acting agent's point of view this IS effectively a silent no-op (an empty "
            "'{}' tool result, indistinguishable from a low-information success, with no row "
            "written) -- consistent with what notification-outward's design relies on -- but the "
            "root cause is a harness-side error-swallowing pattern in ToolMessage construction, "
            "not a database-side silent skip. Both orchestrators (react.py, planner_react.py) "
            "share the identical pattern.",
        ),
        "not_fixed_per_instructions": (
            "external/EnterpriseOps-Gym is vendored/tracked code and out of scope to modify for "
            "this audit; documented here only, as instructed ('characterize precisely, not fix')."
        ),
    }

    evidence = {
        "test": "D_notification_quirk_itsm",
        "quirk_claim_from_RATIONALE_md": (
            "send_notification returns success but creates no row when the recipient is USER_001 "
            "(marcus.thompson@techcorp.com) -- a self-notification guard keyed on that one user."
        ),
        "quirk_confirmed_empirically": quirk_confirmed,
        "mechanism_characterization": mechanism,
        "harness_layer_finding_correcting_RATIONALE_md_silently": harness_layer_finding,
        "replicas": replicas,
        "cross_replica_consistency": consistency,
        "all_steps_consistent_across_replicas": all(c["identical_across_replicas"] for c in consistency.values()),
        "wall_time_s": round(time.time() - t0, 2),
    }
    with open(f"{EVIDENCE_DIR}/test_d_itsm.json", "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True, default=str)
    print(f"\nWrote evidence -> {EVIDENCE_DIR}/test_d_itsm.json")
    print(f"Total wall time: {time.time() - t0:.2f}s")

    print("\nQUIRK CONFIRMED:", quirk_confirmed)
    print("MECHANISM:", mechanism)
    print("\nHARNESS-LAYER CORRECTION TO 'silently no-ops':")
    print(" ", harness_layer_finding["summary"])


if __name__ == "__main__":
    asyncio.run(main())
