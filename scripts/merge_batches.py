#!/usr/bin/env python3
"""Merge verdicts.jsonl from several batches into one model dataset.

Never-splice rule enforced: every task must appear in exactly ONE source batch
with exactly the expected run count; anything else fails loudly.

Usage: merge_batches.py --out runs/<name>-merged --expect-tasks 20 --runs-per-task 8 <batch_dir>...
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--expect-tasks", type=int, required=True)
    ap.add_argument("--runs-per-task", type=int, default=8)
    ap.add_argument("batches", nargs="+", type=Path)
    args = ap.parse_args()

    rows, task_source = [], {}
    for b in args.batches:
        with open(b / "verdicts.jsonl") as f:
            batch_rows = [json.loads(l) for l in f]
        for task in {r["task_id"] for r in batch_rows}:
            if task in task_source:
                raise SystemExit(f"NEVER-SPLICE VIOLATION: {task} in both {task_source[task]} and {b}")
            task_source[task] = str(b)
        rows += batch_rows

    counts = Counter(r["task_id"] for r in rows)
    bad = {t: n for t, n in counts.items() if n != args.runs_per_task}
    if bad:
        raise SystemExit(f"RUN-COUNT VIOLATION: {bad}")
    if len(counts) != args.expect_tasks:
        raise SystemExit(f"TASK-COUNT VIOLATION: {len(counts)} != {args.expect_tasks}: {sorted(counts)}")

    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "verdicts.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    damage = sum(1 for r in rows if r["counts_as_damage"])
    upper = sum(1 for r in rows if r["counts_as_damage_upper"])
    print(f"OK: {args.out} <- {len(counts)} tasks x {args.runs_per_task} = {len(rows)} runs; damage={damage} upper={upper}")
    for t, src in sorted(task_source.items()):
        if counts[t] != args.runs_per_task:
            print("  ", t, "<-", src)


if __name__ == "__main__":
    main()
