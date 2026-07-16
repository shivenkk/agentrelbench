"""
TEST 1 — TOOL INVENTORY

Dump complete tools/list (name, description, inputSchema) for both live MCP
servers and write them to data/eog/tool-inventory-{csm,itsm}.json. Also produce
a first-pass read-only vs state-changing classification by name/description
keyword heuristics, written to m1_audit/evidence/test1_classification.json.

Rerun: /path/to/.venv/bin/python m1_audit/test1_tool_inventory.py
"""
import asyncio
import json
import re
import sys

sys.path.insert(0, "/Users/shiven/Documents/Projects/agentrelbench/m1_audit")
import gym_client as gc

DATA_DIR = "/Users/shiven/Documents/Projects/agentrelbench/data/eog"
EVIDENCE_DIR = "/Users/shiven/Documents/Projects/agentrelbench/m1_audit/evidence"

READ_PREFIXES = (
    "find_", "search_", "get_", "list_", "check_", "view_", "read_", "retrieve_",
    "count_", "avg_", "average_", "total_", "sum_",
)
READ_SUFFIXES = ("_count", "_total")
WRITE_PREFIXES = (
    "create_", "update_", "updated_", "delete_", "remove_", "cancel_", "close_",
    "escalate_", "link_", "assign_", "activate_", "deactivate_", "resolve_",
    "reopen_", "add_", "set_", "send_", "notify_", "merge_", "split_", "attach_",
    "detach_", "upload_", "move_", "copy_", "archive_", "restore_", "approve_",
    "reject_", "decommission_", "escalate", "unassign_", "register_", "enlist_",
)
WRITE_KEYWORDS = (
    "create", "update", "delete", "remove", "cancel", "close ", "escalate", "assign",
    "activate", "deactivate", "resolve", "reopen", "modify", "change ", "set ",
    "send ", "notify", "merge", "attach", "detach", "upload", "move ", "archive",
    "restore", "approve", "reject", "decommission",
)


def classify(name: str, description: str) -> str:
    n = name.lower()
    d = (description or "").lower()
    # read-only checks first: name-shape (prefix/suffix) beats description keyword
    # scanning, since long usage-instruction descriptions can mention unrelated
    # tool verbs (e.g. a read tool's docstring cross-referencing an update_* tool).
    if n.startswith(READ_PREFIXES) or n.endswith(READ_SUFFIXES):
        return "read-only"
    if n.startswith(WRITE_PREFIXES):
        return "state-changing"
    # fall back to description keyword scan
    for kw in WRITE_KEYWORDS:
        if kw in d:
            return "state-changing"
    if re.search(r"\b(retrieve|fetch|lookup|query|list all|search for)\b", d):
        return "read-only"
    return "unclear"


async def dump_domain(label: str, base_url: str):
    client = await gc.new_client(base_url)
    tools = await client.list_tools()
    out_path = f"{DATA_DIR}/tool-inventory-{label}.json"
    with open(out_path, "w") as f:
        json.dump(tools, f, indent=2, sort_keys=True)

    classified = []
    for t in tools:
        name = t.get("name", "")
        desc = t.get("description", "")
        classified.append({"name": name, "description": desc, "class": classify(name, desc)})

    counts = {"total": len(tools)}
    for c in ("read-only", "state-changing", "unclear"):
        counts[c] = sum(1 for x in classified if x["class"] == c)

    return tools, classified, counts, out_path


async def main():
    results = {}
    for label, url in (("csm", gc.CSM_URL), ("itsm", gc.ITSM_URL)):
        tools, classified, counts, out_path = await dump_domain(label, url)
        results[label] = {"counts": counts, "classified": classified, "written_to": out_path}
        print(f"\n=== {label} ({url}) ===")
        print(f"  wrote {len(tools)} tools -> {out_path}")
        print(f"  counts: {counts}")
        print("  state-changing tools:")
        for x in classified:
            if x["class"] == "state-changing":
                print(f"    - {x['name']}: {x['description'][:90]}")
        print("  unclear tools:")
        for x in classified:
            if x["class"] == "unclear":
                print(f"    - {x['name']}: {x['description'][:90]}")

    with open(f"{EVIDENCE_DIR}/test1_classification.json", "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    print(f"\nWrote classification detail -> {EVIDENCE_DIR}/test1_classification.json")


if __name__ == "__main__":
    asyncio.run(main())
