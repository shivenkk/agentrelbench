#!/usr/bin/env python3
"""Write a provenance sidecar for every released verdicts file.

The released verdicts rows carry task_id, run, and outcome, but not model id, k,
serving stack, or date. That makes the files distinguishable only by their path:
rename one and the measurement behind it becomes unreconstructible. A receipt
whose configuration has to be recovered from shell history is not a receipt.

The frozen campaign files are NOT modified. The paper's numbers are records of
runs that already happened, so each released file gets a sidecar
``<name>.manifest.json`` instead.

Lineage is reconstructed rather than trusted: merge_batches.py computed the
task -> source batch map and printed it, but never persisted it. Here each task
in a merged file is matched back to the unique raw batch containing byte-identical
rows for it, which re-proves the never-splice invariant from content and fails
loudly on ambiguity.

Usage: .venv/bin/python scripts/make_data_manifests.py
"""
from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs"

# The files scripts/reproduce.sh needs, i.e. everything the paper's figures and
# Section 5 numbers are computed from.
RELEASED = [
    "campaign-merged/mistral-24b.verdicts.jsonl",
    "campaign-merged/gpt-oss-120b.verdicts.jsonl",
    "campaign-merged/deepseek-v3.2.verdicts.jsonl",
    "frontier-merged/opus-4-6.verdicts.jsonl",
    "frontier-merged/haiku-4-5.verdicts.jsonl",
    "llama8b-merged/verdicts.jsonl",
    "qwen14b-merged/verdicts.jsonl",
    "qwen-merged/verdicts.jsonl",
    "20260716T183218Z_432f84/verdicts.jsonl",
    "20260717T191024Z_147888/verdicts.jsonl",
    # Both arm-C depth batches. The llama-70b one was missing from the release
    # checklist's list of cited batches and was caught by the clean-room run,
    # not by any local test: locally the untracked file is simply present.
    "20260717T155716Z_f2f677/verdicts.jsonl",
    "20260717T160119Z_5daf96/verdicts.jsonl",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_key(row: dict) -> str:
    """Content identity of a single run row, independent of file ordering."""
    return json.dumps(row, sort_keys=True)


def recover_manifest(batch: Path) -> dict:
    """Rebuild what provenance survives for a batch that never wrote a manifest.

    manifest.json is written at batch completion, so any batch that did not run
    to completion has none. The staged job specs still name the LLM config, which
    resolves to a live conf-local file.
    Harness commit, substrate commit, and image digests were never recorded for
    these batches and are reported as unknown rather than guessed.
    """
    specs = sorted((batch / "_staging").glob("*.job_spec.json"))
    if not specs:
        return {"provenance": "none", "unrecorded": ["everything"]}

    loaded = [json.loads(p.read_text()) for p in specs]
    config_paths = {s.get("llm_config_path") for s in loaded}
    ks = {s.get("k") for s in loaded}
    llm = {}
    if len(config_paths) == 1:
        path = Path(config_paths.pop())
        if path.exists():
            cfg = json.loads(path.read_text())
            llm = {"llm_model": cfg.get("llm_model"),
                   "llm_provider": cfg.get("llm_provider")}
            sampling = {"temperature": cfg.get("temperature"),
                        "max_tokens": cfg.get("max_tokens")}
        else:
            sampling = None
    else:
        sampling = None

    return {
        "provenance": "partial",
        "llm_config": llm,
        "sampling_params": sampling,
        "k": ks.pop() if len(ks) == 1 else None,
        "started_at": None,
        "finished_at": None,
        "unrecorded": ["agentrelbench_git_sha", "eog_commit",
                       "mcp_image_digests", "run_window_utc"],
    }


def harness_diff(shas) -> dict:
    """Did the measured-behaviour surface move between these commits?

    The pre-registration voids a model's held-out status if the harness is fixed
    after that model has run, so a file spanning two commits needs this answered,
    not just flagged. Only src/ and the task suite can change behaviour; docs and
    results commits cannot.
    """
    shas = sorted(s for s in shas if s)
    if len(shas) < 2:
        return {}
    changed = set()
    for older, newer in itertools.pairwise(shas):
        try:
            out = subprocess.run(
                ["git", "diff", "--name-only", older, newer,
                 "--", "src", "tasks", "tasks-escalated"],
                cwd=REPO, capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError:
            return {"behaviour_surface_unchanged": None,
                    "note": "commits not resolvable in current history"}
        changed.update(f for f in out.splitlines() if f.strip())
    return {
        "behaviour_surface_unchanged": not changed,
        "behaviour_surface_changed_files": sorted(changed),
        "note": ("src/ and the task suite are byte-identical across these "
                 "commits, so held-out status is intact" if not changed else
                 "the measured surface moved between commits; held-out status "
                 "must be re-argued"),
    }


def load_batches():
    """Index every raw batch by (task_id -> {row_key}) plus its provenance.

    Indexes on verdicts.jsonl, not manifest.json: excluding manifest-less
    batches would silently drop the dev pool, which is the denominator of the
    paper's primary k=1 audit miss rate.
    """
    batches = {}
    for verdicts in sorted(RUNS.glob("*/verdicts.jsonl")):
        batch = verdicts.parent
        if batch.name.endswith("-merged") or batch.name == "quarantine":
            continue
        manifest_path = batch / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            manifest.setdefault("provenance", "complete")
        else:
            manifest = recover_manifest(batch)
        by_task = defaultdict(set)
        for line in verdicts.open():
            row = json.loads(line)
            by_task[row["task_id"]].add(row_key(row))
        batches[batch.name] = {"manifest": manifest, "by_task": by_task}
    return batches


def trace(rel: str, batches: dict) -> dict:
    path = RUNS / rel
    rows = [json.loads(line) for line in path.open()]
    by_task = defaultdict(list)
    for row in rows:
        by_task[row["task_id"]].append(row)

    def candidates(task, task_rows, pool):
        want = {row_key(r) for r in task_rows}
        return [n for n in pool if want <= batches[n]["by_task"].get(task, set())]

    # A clean-pass row carries no model, no deltas, and no distinguishing field,
    # so it is byte-identical across models and matches every batch that ran the
    # task cleanly. Only distinctive tasks (damage, errors, differing success
    # patterns) identify a batch. Anchor on those, then resolve the rest within
    # the identified model. This asymmetry is exactly why the sidecar is needed.
    anchors = {}
    for task, task_rows in sorted(by_task.items()):
        hits = candidates(task, task_rows, batches)
        if len(hits) == 1:
            anchors[task] = hits[0]
    if not anchors:
        raise SystemExit(
            f"{rel}: no task in this file is uniquely traceable by row content, "
            f"so its provenance cannot be established from the released data alone"
        )

    models = {batches[b]["manifest"].get("llm_config", {}).get("llm_model")
              for b in anchors.values()}
    if len(models) != 1:
        raise SystemExit(f"{rel}: anchor tasks disagree on model: {models}")
    model = models.pop()
    pool = [n for n, b in batches.items()
            if b["manifest"].get("llm_config", {}).get("llm_model") == model]

    tasks, sources = {}, {}
    for task, task_rows in sorted(by_task.items()):
        hits = candidates(task, task_rows, pool)
        if len(hits) != 1:
            raise SystemExit(
                f"{rel}: task {task!r} traced to {len(hits)} batches of model "
                f"{model} ({hits or 'none'}); lineage is ambiguous, refusing to "
                f"write a manifest that would assert otherwise"
            )
        tasks[task] = {"k": len(task_rows), "source_batch": hits[0]}
        sources.setdefault(hits[0], []).append(task)

    # Every contributing batch must agree on the serving configuration, or the
    # merged file is not one measurement and must not be described as one.
    def field(name, get):
        """One agreed value across source batches; unrecorded values are not votes."""
        values = {json.dumps(get(batches[b]["manifest"]), sort_keys=True)
                  for b in sources}
        values.discard("null")
        if not values:
            return None
        if len(values) != 1:
            raise SystemExit(f"{rel}: source batches disagree on {name}: {values}")
        return json.loads(values.pop())

    # Digests are a union keyed by server URL, not a single value: a batch pins
    # only the domains its tasks touched (csm only, itsm only, or both). A real
    # conflict is one URL resolving to two different digests.
    digests = {}
    for b in sources:
        for url, digest in (batches[b]["manifest"].get("mcp_image_digests") or {}).items():
            if digests.setdefault(url, digest) != digest:
                raise SystemExit(
                    f"{rel}: {url} pinned to two different images across source "
                    f"batches ({digests[url]} vs {digest}); the substrate moved "
                    f"mid-measurement"
                )

    # Compare identity fields, not the whole config dict: recovered manifests
    # carry only model and provider, complete ones also carry endpoint and
    # sampling, and a shape difference is not a disagreement about what ran.
    llm = {
        "llm_model": field("llm_model",
                           lambda m: (m.get("llm_config") or {}).get("llm_model")),
        "llm_provider": field("llm_provider",
                              lambda m: (m.get("llm_config") or {}).get("llm_provider")),
    }
    stamps = [batches[b]["manifest"].get(f) for b in sources
              for f in ("started_at", "finished_at")]
    stamps = [s for s in stamps if s]
    started, finished = (min(stamps), max(stamps)) if stamps else (None, None)

    unrecorded = sorted({f for b in sources
                         for f in batches[b]["manifest"].get("unrecorded", [])})
    provenance = ("complete"
                  if all(batches[b]["manifest"].get("provenance") == "complete"
                         for b in sources) else "partial")

    return {
        "file": rel,
        "sha256": sha256(path),
        "rows": len(rows),
        "provenance": provenance,
        "unrecorded_fields": unrecorded,
        "model": llm.get("llm_model"),
        "provider": llm.get("llm_provider"),
        "provider_pin": field("provider_pin",
                              lambda m: m.get("provider_pin")),
        "sampling_params": field("sampling_params",
                                 lambda m: m.get("sampling_params")),
        "k_by_task": {t: v["k"] for t, v in tasks.items()},
        "k_values": sorted({v["k"] for v in tasks.values()}),
        "run_window_utc": {"first_started": started, "last_finished": finished},
        # Recorded per batch, not collapsed: the pre-registration voids a model's
        # held-out status if the harness changed after that model ran, so a file
        # spanning two harness commits is a fact a reader must be able to check.
        "agentrelbench_git_sha_by_batch": {
            b: batches[b]["manifest"].get("agentrelbench_git_sha")
            for b in sorted(sources)},
        # Only recorded shas count. An unrecorded sha is missing evidence, not
        # evidence of a second commit.
        "spans_multiple_harness_commits": len({
            batches[b]["manifest"].get("agentrelbench_git_sha")
            for b in sources} - {None}) > 1,
        "harness_diff_across_commits": harness_diff(
            {batches[b]["manifest"].get("agentrelbench_git_sha") for b in sources}),
        # The substrate must not move mid-measurement, so this stays strict.
        "eog_commit": field("eog_commit", lambda m: m.get("eog_commit")),
        "mcp_image_digests": digests,
        "source_batches": {b: sorted(ts) for b, ts in sorted(sources.items())},
        "never_splice": "each task traced to exactly one source batch by row content",
        "git_sha_scope": (
            "agentrelbench_git_sha values were recorded at run time against the "
            "pre-publication development history, which was rewritten before "
            "release. They are the true provenance of each batch but do not "
            "resolve in the published repository. Any harness comparison below "
            "was performed while they still resolved and is recorded here rather "
            "than left to be recomputed."
        ),
        "lineage_method": (
            f"{len(anchors)} of {len(tasks)} tasks are uniquely traceable by row "
            "content and anchor the model; the remainder are clean-pass cells "
            "whose rows are byte-identical across models and were resolved within "
            "that model's batches"
        ),
    }


def main() -> int:
    batches = load_batches()
    print(f"indexed {len(batches)} raw batches under runs/")

    for rel in RELEASED:
        if not (RUNS / rel).exists():
            raise SystemExit(f"released file missing: runs/{rel}")
        man = trace(rel, batches)
        out = (RUNS / rel).with_suffix(".manifest.json")
        out.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n")
        print(f"  {rel}")
        print(f"      model={man["model"]} provider={man["provider"]} "
              f"k={man['k_values']} rows={man['rows']} "
              f"batches={len(man['source_batches'])}")
    print(f"\nwrote {len(RELEASED)} manifests; frozen verdicts files untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
