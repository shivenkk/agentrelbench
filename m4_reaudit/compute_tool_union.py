"""
M4 STEP 0, TOOL UNION + SEED-FILE CONSISTENCY

Computes the union of `selected_tools` across every task.json under
tasks/{csm,itsm}/*/task.json (the finalized 20-task portfolio), and cross-checks
that every task within a domain references the identical seed_database_file
(so the M1 audit's fixed CSM_SEED/ITSM_SEED constants in gym_client.py are
still the right seeds to re-run against).

Writes data/eog/tool-union-{csm,itsm}.json (per-task selected_tools + the
union + per-tool tag lookup from tool-tags-*.json, partitioned mutating vs
read-only) for downstream scripts (test_a_mutating_determinism_*.py etc.) to
import instead of recomputing.

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/compute_tool_union.py
"""
import json
import glob
import os

ROOT = "/Users/shiven/Documents/Projects/agentrelbench"
DATA_DIR = f"{ROOT}/data/eog"


def load_tags(domain):
    d = json.load(open(f"{DATA_DIR}/tool-tags-{domain}.json"))
    return {t["name"]: t for t in d["tags"]}


def main():
    for domain in ("csm", "itsm"):
        task_paths = sorted(glob.glob(f"{ROOT}/tasks/{domain}/*/task.json"))
        tags = load_tags(domain)

        per_task = {}
        seed_files = set()
        union = set()
        for p in task_paths:
            task_name = os.path.basename(os.path.dirname(p))
            d = json.load(open(p))
            tools = d.get("selected_tools", [])
            per_task[task_name] = tools
            union.update(tools)
            for cfg in d.get("gym_servers_config", []):
                seed_files.add(cfg.get("seed_database_file"))

        union = sorted(union)
        tagged = {}
        untagged = []
        for t in union:
            if t in tags:
                tagged[t] = tags[t]
            else:
                untagged.append(t)

        mutating = sorted(t for t in union if t in tags and tags[t]["tag"] != "read")
        read_only = sorted(t for t in union if t in tags and tags[t]["tag"] == "read")

        out = {
            "domain": domain,
            "num_tasks": len(task_paths),
            "task_names": [os.path.basename(os.path.dirname(p)) for p in task_paths],
            "per_task_selected_tools": per_task,
            "union_count": len(union),
            "union": union,
            "seed_files_referenced": sorted(seed_files),
            "single_seed_file_confirmed": len(seed_files) == 1,
            "mutating_tools": mutating,
            "mutating_count": len(mutating),
            "read_only_tools": read_only,
            "read_only_count": len(read_only),
            "untagged_tools": untagged,
        }
        out_path = f"{DATA_DIR}/tool-union-{domain}.json"
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2, sort_keys=True)

        print(f"=== {domain} ===")
        print(f"  tasks: {len(task_paths)} -> {out['task_names']}")
        print(f"  seed files referenced: {seed_files}")
        print(f"  union size: {len(union)}")
        print(f"  mutating ({len(mutating)}): {mutating}")
        print(f"  read-only ({len(read_only)}): {read_only}")
        if untagged:
            print(f"  UNTAGGED (not in tool-tags-{domain}.json !!): {untagged}")
        print(f"  wrote -> {out_path}\n")


if __name__ == "__main__":
    main()
