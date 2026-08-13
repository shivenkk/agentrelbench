#!/usr/bin/env python3
"""Derive the provider-pin evidence from the campaign logs into a public manifest.

The paper states that every held-out model ran under the same pinned serving
configuration. The evidence is a banner the harness prints once per pinned worker
process, and it survives only in the campaign driver logs under runs/, which are
untracked and will stay that way: they are full agent transcripts, so publishing
them would put an oracle path for every task into a searchable public artifact.

The released verdicts sidecars cannot stand in for them. Their provenance was
recovered from staged job specs after the fact, and every campaign sidecar
records ``provider_pin: null`` -- the pin was set in the runner's environment,
not in the LLM config a sidecar could read back. The logs are the only surviving
record of it.

So this extracts the claim's evidence instead of the transcripts: per-cell banner
counts, the pinned provider, and a sha256 of every source log, so a reader who
later obtains a log can confirm the extraction was not massaged.

Three things separate this from a grep, and each fails loudly rather than being
reported as a caveat:

  1. A banner proves the pin was installed in one worker process, which says
     nothing about the runs in the log unless every run block sits downstream of
     one. The segments between banners must account for all of them.
  2. OpenRouter echoes the endpoint it served in its error metadata. Any provider
     there other than the cell's pin would mean the pin did not hold, so the
     errored payloads are checked rather than skipped as noise.
  3. The expected shape of the campaign is frozen below, so the extractor cannot
     quietly report a different campaign than the one the paper describes.

Output is a pure function of the logs -- no timestamps -- so an unchanged set of
logs regenerates a byte-identical manifest.

Usage: .venv/bin/python scripts/extract_provider_pins.py
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs"
RUNNER = REPO / "src" / "agentrelbench" / "inner_runner.py"
OUT = REPO / "docs" / "provider-pin-manifest.md"

# Printed once per pinned worker process by inner_runner.py, immediately after
# the ChatOpenAI rebinding takes effect and before any request is constructed.
BANNER = re.compile(r"\[agentrelbench\] provider pinned: (\S+) \(allow_fallbacks=(\w+)\)")

# One per evaluate.py invocation, i.e. one per run. Emitted when the run's client
# is configured, so it is the first point at which an unpinned request could
# exist -- which makes it the right unit for the coverage check.
RUN_START = re.compile(r"Using LLM config: (\S+)")

MODEL = re.compile(r"benchmark\.executor - INFO - Model: (\S+)")

# OpenRouter's error metadata names the endpoint it served, or None when the
# request was rejected before an endpoint was chosen.
PROVIDER_NAME = re.compile(r"'provider_name': (None|'[^']*')")
CONTEXT_LIMIT = re.compile(r"maximum context length is (\d+) tokens")
REQUESTED = re.compile(r"you requested about (\d+) tokens")

CELL = re.compile(r"^camp-([a-z0-9]+)-([a-z0-9]+)\.log$")

MODELS = ["mistral", "oss", "deepseek"]
ARMS = ["breadth", "depth5", "cab"]

# Frozen after verification against the logs. Each entry is
# (pinned provider, banners i.e. pinned worker processes, runs covered).
EXPECTED = {
    ("mistral", "breadth"): ("DeepInfra", 14, 112),
    ("mistral", "depth5"): ("DeepInfra", 5, 80),
    ("mistral", "cab"): ("DeepInfra", 1, 16),
    ("oss", "breadth"): ("DeepInfra", 14, 112),
    ("oss", "depth5"): ("DeepInfra", 5, 80),
    ("oss", "cab"): ("DeepInfra", 1, 32),
    ("deepseek", "breadth"): ("AtlasCloud", 14, 112),
    ("deepseek", "depth5"): ("AtlasCloud", 5, 80),
    ("deepseek", "cab"): ("AtlasCloud", 1, 32),
}

EXPECTED_SLUG = {
    "mistral": "openrouter/mistralai/mistral-small-3.2-24b-instruct",
    "oss": "openrouter/openai/gpt-oss-120b",
    "deepseek": "openrouter/deepseek/deepseek-v3.2",
}

ENDPOINT = "https://openrouter.ai/api/v1"

# The released dataset for each held-out model. Counting these closes the gap
# between "these logs show pinned runs" and "every run behind the paper's
# held-out numbers was pinned": if a model's released row count exceeded the runs
# the logs cover, some released run came from somewhere these banners do not
# reach, and the claim would be about most of the data rather than all of it.
MERGED = {
    "mistral": "campaign-merged/mistral-24b.verdicts.jsonl",
    "oss": "campaign-merged/gpt-oss-120b.verdicts.jsonl",
    "deepseek": "campaign-merged/deepseek-v3.2.verdicts.jsonl",
}

MISSING = """\
runs/camp-*.log not found.

This extractor reads the campaign driver logs, which are untracked local
artifacts: runs/ is gitignored because the logs are full agent transcripts and
publishing them would expose an oracle path for every task.

Its output, docs/provider-pin-manifest.md, IS committed and is what a third
party is meant to read. The logs can be requested from the authors; the sha256
list in the manifest is what makes a received log checkable against it.
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan(path: Path) -> dict:
    """Everything the manifest reports about one campaign log, derived from it."""
    text = path.read_text(errors="replace")

    banners = [(m.start(), m.group(1), m.group(2)) for m in BANNER.finditer(text)]
    if not banners:
        raise SystemExit(
            f"{path.name}: no pin banner in this log, so it is not evidence of a "
            f"pinned run; refusing to write a manifest row that would imply it is"
        )

    runs = [m.start() for m in RUN_START.finditer(text)]

    # Coverage: no run may precede the first banner, and the segments between
    # banners must account for every run. Together these say each run block in
    # this log ran inside a process that had already installed the pin.
    before = sum(1 for r in runs if r < banners[0][0])
    covered = 0
    for i, (off, _, _) in enumerate(banners):
        nxt = banners[i + 1][0] if i + 1 < len(banners) else len(text)
        covered += sum(1 for r in runs if off < r < nxt)

    return {
        "log": path.name,
        "sha256": sha256(path),
        "banners": len(banners),
        "providers": sorted({p for _, p, _ in banners}),
        "fallbacks": sorted({f for _, _, f in banners}),
        "runs": len(runs),
        "runs_before_first_banner": before,
        "runs_covered": covered,
        "endpoints": sorted(set(RUN_START.findall(text))),
        "models": sorted(set(MODEL.findall(text))),
        "errored": errored_payloads(text),
    }


def errored_payloads(text: str) -> list[dict]:
    """Provider attribution recorded in OpenRouter's 400 payloads.

    A pinned endpoint that cannot serve a request must fail, not reroute. These
    payloads are where a reroute would show up, so they are the reason the pin is
    checkable at all rather than merely declared.
    """
    rows = []
    for line in text.splitlines():
        m = PROVIDER_NAME.search(line)
        if not m:
            continue
        if "failed with error" not in line:
            raise SystemExit(
                "provider_name appeared outside an error payload; the reroute "
                f"check assumes error context and does not hold here: {line[:200]}"
            )
        raw = m.group(1)
        limit = CONTEXT_LIMIT.search(line)
        rows.append({
            "provider": None if raw == "None" else raw.strip("'"),
            "kind": "context-length overflow" if limit else "provider returned error",
            "limit": int(limit.group(1)) if limit else None,
            "requested": int(REQUESTED.search(line).group(1)) if limit else None,
        })
    return rows


def released_rows() -> dict:
    """Runs in each held-out model's released verdicts file."""
    counts = {}
    for model, rel in MERGED.items():
        path = RUNS / rel
        if not path.exists():
            raise SystemExit(
                f"runs/{rel} not found. The extractor compares the pinned runs in "
                f"the logs against the released dataset, so it needs both; see "
                f"docs/provider-pin-manifest.md for the committed result."
            )
        counts[model] = sum(1 for line in path.open() if line.strip())
    return counts


def verify(cells: dict, released: dict) -> None:
    """Every claim the manifest makes, re-proved from the scan. Loud on failure."""
    def bad(msg):
        raise SystemExit(f"PIN EVIDENCE VIOLATION: {msg}")

    if set(cells) != set(EXPECTED):
        bad(f"campaign cells are {sorted(cells)}, expected {sorted(EXPECTED)}")

    for key in sorted(EXPECTED):
        model, arm = key
        c = cells[key]
        provider, banners, runs = EXPECTED[key]

        if len(c["providers"]) != 1:
            bad(f"{c['log']}: {len(c['providers'])} distinct providers "
                f"{c['providers']}; a cell served by more than one provider is not "
                f"one serving configuration")
        if c["providers"][0] != provider:
            bad(f"{c['log']}: pinned to {c['providers'][0]}, expected {provider}")
        if c["fallbacks"] != ["false"]:
            bad(f"{c['log']}: allow_fallbacks values {c['fallbacks']}; every banner "
                f"must report false or the pin permitted a silent reroute")
        if c["banners"] != banners:
            bad(f"{c['log']}: {c['banners']} banners, expected {banners}")
        if c["runs"] != runs:
            bad(f"{c['log']}: {c['runs']} runs, expected {runs}")
        if c["runs_before_first_banner"]:
            bad(f"{c['log']}: {c['runs_before_first_banner']} run(s) precede the "
                f"first banner, so they ran unpinned")
        if c["runs_covered"] != c["runs"]:
            bad(f"{c['log']}: {c['runs_covered']} of {c['runs']} runs are downstream "
                f"of a banner; the remainder are not covered by any pin")
        if c["endpoints"] != [ENDPOINT]:
            bad(f"{c['log']}: endpoints {c['endpoints']}, expected [{ENDPOINT}]")
        if c["models"] != [EXPECTED_SLUG[model]]:
            bad(f"{c['log']}: models {c['models']}, expected "
                f"[{EXPECTED_SLUG[model]}]")

        # The reroute check. A named provider in an error payload that is not this
        # cell's pin is the one observation that would falsify the paper's claim.
        foreign = sorted({e["provider"] for e in c["errored"]
                          if e["provider"] and e["provider"] != provider})
        if foreign:
            bad(f"{c['log']}: errored payloads name {foreign}, which is not the "
                f"pinned provider {provider}; the request was rerouted")

    total = sum(c["banners"] for c in cells.values())
    if total != sum(e[1] for e in EXPECTED.values()):
        bad(f"{total} banners across the campaign, expected "
            f"{sum(e[1] for e in EXPECTED.values())}")

    # Released rows must be exactly the runs the banners cover. Fewer would mean
    # the logs carry runs that never reached the dataset; more would mean a
    # released run this evidence does not reach.
    for model in MODELS:
        pinned = sum(c["runs_covered"] for (m, _), c in cells.items() if m == model)
        if pinned != released[model]:
            bad(f"{model}: {pinned} pinned runs in the logs but "
                f"{released[model]} rows in runs/{MERGED[model]}; the pin evidence "
                f"does not account for the released data")


def mechanism() -> dict:
    """Locate the pin in the published source rather than citing line numbers blind.

    The manifest points a reader at the code that produced the banners. Line
    numbers drift, so they are read out of the file here and asserted unique;
    the matching source line is quoted alongside so the citation survives a shift.
    """
    lines = RUNNER.read_text().splitlines()

    def locate(needle):
        hits = [i for i, line in enumerate(lines, 1) if needle in line]
        if len(hits) != 1:
            raise SystemExit(
                f"{RUNNER.relative_to(REPO)}: {needle!r} found {len(hits)} times; "
                f"the manifest cannot cite an ambiguous location"
            )
        return hits[0], lines[hits[0] - 1].strip()

    start, _ = locate("# Provider pinning: when")
    env, env_src = locate('pin = os.environ.get("ARB_PIN_PROVIDER")')
    order, order_src = locate('eb["provider"] = {"order": [pin]')
    banner, banner_src = locate('print(f"[agentrelbench] provider pinned:')
    if not start < env < order < banner:
        raise SystemExit("pin block lines are out of order; check inner_runner.py")
    return {
        "file": str(RUNNER.relative_to(REPO)),
        "span": (start, banner),
        "env": (env, env_src),
        "order": (order, order_src),
        "banner": (banner, banner_src),
    }


def render(cells: dict, mech: dict, released: dict) -> str:
    """The manifest. Generated only -- hand edits are overwritten on regeneration."""
    total_banners = sum(c["banners"] for c in cells.values())
    total_runs = sum(c["runs"] for c in cells.values())
    providers = sorted({c["providers"][0] for c in cells.values()})

    out = [
        "# Provider-pin manifest",
        "",
        "Evidence that every held-out model ran under one pinned serving",
        "configuration: a single OpenRouter provider per model, with",
        "`allow_fallbacks=false`, for every run in the campaign.",
        "",
        f"Across the {len(cells)} campaign cells there are **{total_banners} pin",
        f"banners covering {total_runs} runs**, one distinct provider per cell",
        f"({', '.join(providers)}), and `allow_fallbacks=false` in every banner.",
        "",
        "## What is being read, and why it is not simply published",
        "",
        "The pin banner is printed once per pinned worker process, before that",
        "process constructs any request; the process then executes every run of one",
        "task. The banners live in the campaign driver logs (`runs/camp-*.log`),",
        "which are untracked: `runs/` is gitignored because the logs are full agent",
        "transcripts and publishing them would expose an oracle path for every task",
        "to anyone searching the repository.",
        "",
        "The released verdicts sidecars are not a substitute. Their provenance was",
        "recovered from staged job specs after the fact, and each campaign sidecar",
        "records `provider_pin: null`, because the pin was set in the runner's",
        "environment rather than in the LLM config a sidecar could read back. These",
        "logs are the only surviving record of it.",
        "",
        "This manifest is therefore a derived artifact: counts and identifiers, no",
        "transcript content.",
        "",
        "## How it was produced",
        "",
        "```",
        ".venv/bin/python scripts/extract_provider_pins.py",
        "```",
        "",
        "The script re-derives every number below from the logs and exits non-zero",
        "if any of them fails to hold, so this file cannot be edited into agreement",
        "with a claim the logs do not support. Its output is a pure function of the",
        "logs and carries no generation timestamp, so an unchanged set of logs",
        "regenerates it byte for byte.",
        "",
        "Three properties are asserted beyond the raw counts:",
        "",
        "- **Coverage.** A banner proves a pin was installed in one process, not",
        "  that the runs in the log used it. Every run block is required to sit",
        "  downstream of a banner, with none preceding the first one.",
        "- **No reroute.** OpenRouter names the endpoint it served in its error",
        "  metadata. Any provider there other than the cell's pin fails the script.",
        "- **Shape.** The expected provider, banner count and run count of each cell",
        "  are frozen in the script, so it cannot quietly describe a different",
        "  campaign than the paper does.",
        "",
        "Coverage is also checked against the released data rather than only within",
        "the logs. The runs the banners cover match each model's released verdicts",
        "file exactly ("
        + ", ".join(f"{m} {released[m]}" for m in MODELS)
        + f"; {sum(released.values())} in total), so no",
        "released held-out run falls outside this evidence.",
        "",
        "## Per-cell evidence",
        "",
        "| Cell | Model | Source log | Banners | Runs covered | Pinned provider | `allow_fallbacks` | Distinct providers |",
        "| --- | --- | --- | ---: | ---: | --- | --- | ---: |",
    ]

    for model in MODELS:
        for arm in ARMS:
            c = cells[(model, arm)]
            out.append(
                f"| {model} / {arm} | `{c['models'][0]}` | `{c['log']}` | "
                f"{c['banners']} | {c['runs_covered']} / {c['runs']} | "
                f"{c['providers'][0]} | `{c['fallbacks'][0]}` | "
                f"{len(c['providers'])} |"
            )

    out += [
        "",
        f"All {len(cells)} cells served from `{ENDPOINT}`. Banners count pinned",
        "worker processes, one per task, so runs per banner is that task's k: 14",
        "breadth tasks at k=8, 5 depth tasks at k=16, and the flagship CAB task in a",
        "single process at k=32, except mistral where CAB is k=16.",
        "",
        "## Source log digests",
        "",
        "sha256 of each log as read. A reader who obtains a log from the authors",
        "can check it against this list and re-run the extractor on it.",
        "",
        "```",
    ]
    for key in sorted(cells, key=lambda k: cells[k]["log"]):
        out.append(f"{cells[key]['sha256']}  runs/{cells[key]['log']}")
    out.append("```")

    # The anomaly section. Written from the scan rather than described from
    # memory, so it tracks the logs if they are ever re-extracted.
    errored = {k: c["errored"] for k, c in cells.items() if c["errored"]}
    out += ["", "## Errored payloads: what a pinned endpoint does when it cannot serve", ""]
    if not errored:
        out.append("No campaign log carries an OpenRouter error payload.")
    else:
        for key in sorted(errored, key=lambda k: cells[k]["log"]):
            rows = errored[key]
            pinned = cells[key]["providers"][0]
            named = [e for e in rows if e["provider"]]
            unattributed = [e for e in rows if not e["provider"]]
            out += [
                f"`{cells[key]['log']}` contains {len(rows)} OpenRouter 400 payloads "
                f"carrying a `provider_name`:",
                "",
                f"- **{len(named)} attributed to {pinned}**, the pinned provider: "
                f"`Provider returned error` / `bad request`.",
            ]
            if unattributed:
                limits = sorted({e["limit"] for e in unattributed})
                lo = min(e["requested"] for e in unattributed)
                hi = max(e["requested"] for e in unattributed)
                out.append(
                    f"- **{len(unattributed)} with `provider_name: None`**: "
                    f"context-length overflow. The pinned endpoint's limit is "
                    f"{', '.join(f'{n:,}' for n in limits)} tokens and the request "
                    f"was about {lo:,}-{hi:,} tokens, so OpenRouter rejected it "
                    f"before an endpoint was engaged, leaving nothing to attribute."
                )
            out += [
                "",
                "This is the pin working, not failing. Without it, a request the",
                "pinned endpoint could not serve would have been rerouted to a",
                "provider with a larger context window and the run would have",
                "succeeded under a different serving stack, silently. Pinned, it",
                "fails, and the failure is recorded as an errored run that feeds the",
                "upper-bound estimator instead of contaminating the comparison.",
                "",
                "No payload in any campaign log names a provider other than that",
                "cell's pin, which is the observation that would have falsified the",
                "claim.",
            ]

    out += [
        "",
        "## The mechanism, in the published source",
        "",
        f"`{mech['file']}` lines {mech['span'][0]}-{mech['span'][1]}. When",
        "`ARB_PIN_PROVIDER` is set, the runner subclasses `ChatOpenAI` and rebinds",
        "the module attribute, so every OpenRouter request the substrate makes",
        "carries the provider block; the banner is printed only on that path.",
        "",
        f"- line {mech['env'][0]}: `{mech['env'][1]}`",
        f"- line {mech['order'][0]}: `{mech['order'][1]}`",
        f"- line {mech['banner'][0]}: `{mech['banner'][1]}`",
        "",
        "The banners quoted in this manifest are the runtime output of that last",
        "line, which is reached only after the rebinding above it has taken effect.",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    logs = sorted(RUNS.glob("camp-*.log")) if RUNS.is_dir() else []
    if not logs:
        raise SystemExit(MISSING)

    cells = {}
    for path in logs:
        m = CELL.match(path.name)
        if not m:
            raise SystemExit(f"{path.name}: not a recognizable campaign cell log")
        key = (m.group(1), m.group(2))
        if key in cells:
            raise SystemExit(f"two logs claim cell {key}")
        cells[key] = scan(path)

    released = released_rows()
    verify(cells, released)

    print(f"== {len(cells)} campaign cells, {len(logs)} logs ==")
    for model in MODELS:
        for arm in ARMS:
            c = cells[(model, arm)]
            print(f"  {model + '/' + arm:18s} {c['providers'][0]:11s} "
                  f"allow_fallbacks={c['fallbacks'][0]} "
                  f"banners={c['banners']:2d} runs={c['runs_covered']}/{c['runs']} "
                  f"providers={len(c['providers'])} errored={len(c['errored'])}")
    print(f"  {'total':18s} {sum(c['banners'] for c in cells.values())} banners, "
          f"{sum(c['runs'] for c in cells.values())} runs, "
          f"{sum(len(c['errored']) for c in cells.values())} errored payloads")
    print(f"  {'released rows':18s} "
          + ", ".join(f"{m}={released[m]}" for m in MODELS)
          + f" (total {sum(released.values())}), all accounted for")

    OUT.write_text(render(cells, mechanism(), released))
    print(f"\nwrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
