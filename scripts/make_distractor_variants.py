#!/usr/bin/env python3
"""Arm A generator: plus-10 distractor variants of the quiet intermediate tasks.

Escalation lever pre-registered in docs/task-design-m4.md §1.2/§4 and armed by
the M5 gate GO (decision log 2026-07-17). For each task, appends 10 distractor
tools to `selected_tools`, drawn ONLY from the determinism-audited union
(data/eog/tool-union-<domain>.json), the M4 gate rule: no unaudited tool may
enter the reachable surface without a fresh audit.

Selection is deterministic per task (seeded by task name): prefer MUTATING
near-miss tools sharing an entity token with the task's own tools (the
confusable surface is the point), then other mutating, then reads. Damage
specs are copied UNCHANGED except task_id/rationale, whitelists are about
state, not tools, so any damage newly reachable through a distractor is
caught by the closed world automatically.

Usage: .venv/bin/python scripts/make_distractor_variants.py
Writes: tasks-escalated/<domain>/<name>__plus10/{task.json,damage.json}
        scratch/pilot-tasks-arm-a/<name>__plus10.json
"""
import json
import random
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
N_DISTRACTORS = 10
MIN_MUTATING = 4

ARM_A_TASKS = [
    "account-onboarding-chain", "ci-cost-correction", "contract-price-correction",
    "contract-renewal-enlist", "entitlement-update-dead-contract", "incident-sla-cleanup",
    "installed-product-serial", "notification-cleanup", "notification-outward",
    "parent-child-restructure", "problem-change-mapping", "product-price-sync",
    "template-driven-incidents",
]


def entity_tokens(tool_names):
    toks = set()
    for n in tool_names:
        toks.update(t for t in re.split(r"[_/]", n) if len(t) > 3)
    return toks - {"find", "list", "update", "create", "delete", "count", "search", "with"}


def load_union(domain):
    raw = json.loads((REPO / f"data/eog/tool-union-{domain}.json").read_text())
    return raw if isinstance(raw, list) else raw.get("tools", raw.get("union", []))


def load_tags(domain):
    raw = json.loads((REPO / f"data/eog/tool-tags-{domain}.json").read_text())
    return {t["name"]: t["tag"] for t in raw["tags"]}


def pick_distractors(task_name, base_tools, domain):
    rng = random.Random(f"arm-a::{task_name}")
    union = [t for t in load_union(domain) if t not in base_tools]
    tags = load_tags(domain)
    toks = entity_tokens(base_tools)

    def bucket(t):
        mutating = tags.get(t, "read") != "read"
        near = bool(entity_tokens([t]) & toks)
        if mutating and near:
            return 0
        if mutating:
            return 1
        return 2

    by_bucket = {0: [], 1: [], 2: []}
    for t in sorted(union):
        by_bucket[bucket(t)].append(t)
    for b in by_bucket.values():
        rng.shuffle(b)

    picked = []
    # guarantee the mutating floor first (near-miss mutating, then other mutating)
    for b in (0, 1):
        for t in by_bucket[b]:
            if len([p for p in picked if tags.get(p, "read") != "read"]) >= MIN_MUTATING:
                break
            picked.append(t)
    # fill the rest interleaving reads and leftover mutating
    rest = [t for t in by_bucket[0] + by_bucket[1] + by_bucket[2] if t not in picked]
    picked += rest[: N_DISTRACTORS - len(picked)]
    return picked[:N_DISTRACTORS]


def main():
    staging = REPO / "scratch/pilot-tasks-arm-a"
    staging.mkdir(parents=True, exist_ok=True)
    for name in ARM_A_TASKS:
        src_candidates = list((REPO / "tasks").glob(f"*/{name}"))
        assert len(src_candidates) == 1, (name, src_candidates)
        src = src_candidates[0]
        domain = json.loads((src / "damage.json").read_text())["domain"]

        task = json.loads((src / "task.json").read_text())
        base_tools = list(task["selected_tools"])
        distractors = pick_distractors(name, base_tools, domain)
        task["selected_tools"] = base_tools + distractors

        dmg = json.loads((src / "damage.json").read_text())
        dmg["task_id"] = f"{dmg['task_id']}__plus10"
        dmg["predicted_lever"]["rationale"] += " [plus10 escalation: 10 audited distractor tools added]"

        out = REPO / "tasks-escalated" / domain / f"{name}__plus10"
        out.mkdir(parents=True, exist_ok=True)
        (out / "task.json").write_text(json.dumps(task, indent=2))
        (out / "damage.json").write_text(json.dumps(dmg, indent=2))
        # Oracle + counterexamples reference only base tools -> valid for variants;
        # copying keeps every variant independently arb-validate-able.
        shutil.copy(src / "oracle.script.json", out / "oracle.script.json")
        if (src / "counterexamples").is_dir():
            shutil.copytree(src / "counterexamples", out / "counterexamples", dirs_exist_ok=True)
        shutil.copy(out / "task.json", staging / f"{name}__plus10.json")
        n_mut = sum(1 for t in distractors if load_tags(domain).get(t, "read") != "read")
        print(f"{name}__plus10: +{len(distractors)} distractors ({n_mut} mutating): {distractors}")


if __name__ == "__main__":
    main()
