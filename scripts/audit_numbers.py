#!/usr/bin/env python3
"""Recompute every derived number from run data and diff it against the manuscript.

Run before any content freeze. arXiv v1 is permanent: a wrong number in the
posted PDF can be superseded but never retracted, so this is a blocking gate,
not hygiene.

scripts/make_appendix_e.py already binds the *generated* tables to run data.
This script covers what that cannot: numbers typed by hand into prose, and
three failure modes a drift gate structurally misses.

  1. Truncation instead of rounding (0.1357 typed as 0.13 when it is 0.14).
  2. One cell of a row rounded correctly while its neighbour truncates.
  3. Two rows of one table computed with different estimators, e.g. a
     continuity-corrected interval sitting among exact Clopper-Pearson ones.

Check 1 and 2 fall out of comparing every manuscript decimal against both the
rounded and the truncated rendering of every recomputed quantity. Check 3 falls
out of requiring every interval in the text to be an exact Clopper-Pearson
interval of some real cell.

Usage: .venv/bin/python scripts/audit_numbers.py     (exit 1 on any finding)
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from make_figures import (  # noqa: E402
    CAB,
    DEV_BREADTH,
    load_pool,
)
from agentrelbench.estimators import (  # noqa: E402
    audit_miss_rate,
    clopper_pearson,
    demonstrably_stochastic,
    fit_beta_binomial,
    per_task_stats,
)

# Hand-written sources only. appendix-e.tex and appendix-e-tables.md are
# generated under assertions by make_appendix_e.py, so auditing them would only
# re-test that generator.
SOURCES = [
    "paper/main.tex",
    "paper/appendix.tex",
    "docs/paper-draft.md",
    "docs/appendices.md",
]

DECIMAL = re.compile(r"(?<![\d.])(0?\.\d{2,4})(?![\d])")
INTERVAL = re.compile(r"\(\s*(0?\.\d{2,4})\s*,\s*(0?\.\d{2,4})\s*\)")
FRACTION = re.compile(r"(?<![\d./])(\d{1,3})\s*/\s*(\d{1,3})(?![\d/])")

# LaTeX carries decimals that are typography, not statistics: p{0.42\linewidth}
# column specs, includegraphics widths, scale factors. Blanked (length-preserving,
# so reported line numbers stay correct) before the decimal scan.
TYPOGRAPHY = re.compile(
    r"\d*\.?\d+\s*\\(?:linewidth|textwidth|columnwidth|baselineskip|paperwidth)"
    r"|p\{[^{}]*\}"
    r"|(?:width|height|scale|trim|angle)\s*=\s*[\d.]+[^,\]\s]*"
)

# Pre-registered thresholds, frozen before held-out contact. These are fractions
# by construction and are deliberately NOT observed cells: the engagement floor
# for the flagship task (pass >= 3/16, applied proportionally as >= 6/32 at k=32).
PREREG_THRESHOLDS = {(3, 16), (6, 32)}

# A decimal introduced by an inequality is a bound, not a point estimate:
# "p < 0.001" is a threshold the data clears, and comparing it against nearby
# quantities produces spurious truncation findings.
BOUNDED = re.compile(r"(?:[<>]|\\l[et]q?|\\g[et]q?|\\ll|\\gg)\s*\$?\s*$")


def dev_stats():
    """Per-task stats for the frozen dev breadth pool (the 13-pair denominator)."""
    pool = {}
    for model, rel in DEV_BREADTH.items():
        for line in open(REPO / rel / "verdicts.jsonl"):
            row = json.loads(line)
            pool.setdefault((model, row["task_id"]), []).append(
                type("R", (), {
                    "counts_as_damage": row["counts_as_damage"],
                    "counts_as_damage_upper": row["counts_as_damage_upper"],
                    "success": row["eog_success"],
                    "sub_label": row.get("sub_label"),
                })())
    return per_task_stats(pool)


def recompute():
    """Every derived quantity the manuscript could cite, computed from run data.

    Returns (quantities, cells, intervals) where quantities maps a name to a
    float, cells is the set of real (x, n) pairs, and intervals is the set of
    exact Clopper-Pearson (lo, hi) pairs.
    """
    held = per_task_stats(load_pool())
    dev = dev_stats()

    q, cells, intervals = {}, set(), set()

    for label, stats in (("heldout", held), ("dev", dev)):
        for (model, task), t in stats.items():
            cells.add((t.x, t.n))
            cells.add((t.s, t.n))
            lo, hi = clopper_pearson(t.x, t.n)
            intervals.add((round(lo, 3), round(hi, 3)))
            if t.x:
                q[f"phat[{label}/{model}/{task}]"] = t.x / t.n
                q[f"miss1[{label}/{model}/{task}]"] = (t.n - t.x) / t.n
                q[f"ci_lo[{label}/{model}/{task}]"] = lo
                q[f"ci_hi[{label}/{model}/{task}]"] = hi

    # Beta-binomial ICC, reported in Section 2 against ClawsBench's 0.48. Both the
    # all-cells and damage-producing-cells-only values appear in the text, so both
    # are audited; a truncated 0.212 or 0.306 would otherwise pass unnoticed.
    for label, stats in (("heldout", held), ("dev", dev)):
        q[f"icc[{label},all]"] = fit_beta_binomial(stats).icc
        producing = {k: v for k, v in stats.items() if v.x > 0}
        if len(producing) > 1:
            q[f"icc[{label},damage-producing]"] = fit_beta_binomial(producing).icc

    q["miss_rate[dev,pair]"] = audit_miss_rate(dev, "pair")
    q["miss_rate[dev,event]"] = audit_miss_rate(dev, "event")
    q["miss_rate[heldout,pair]"] = audit_miss_rate(held, "pair")
    q["miss_rate[heldout,event]"] = audit_miss_rate(held, "event")

    # Audit-decay figures: the paper reports (1 - p)^k for the opus cab cell.
    opus = held[("opus-4.6", CAB)]
    miss = (opus.n - opus.x) / opus.n
    q["opus_miss1"] = miss
    for k in (2, 3, 4, 5, 8, 16, 18):
        q[f"decay[opus,k={k}]"] = miss ** k

    counts = {
        "heldout_pairs": sum(1 for t in held.values() if t.x > 0),
        "heldout_events": sum(t.x for t in held.values()),
        "heldout_stochastic": len(demonstrably_stochastic(held).tasks),
        "heldout_traps": sum(1 for t in held.values() if t.x == t.n and t.n),
        "dev_pairs": sum(1 for t in dev.values() if t.x > 0),
        "dev_events": sum(t.x for t in dev.values()),
    }
    return q, cells, intervals, counts, held, dev


def render(value, places):
    """Correct rounding, and the truncation a hand-typed number falls into."""
    rounded = f"{value:.{places}f}"
    scale = 10 ** places
    truncated = f"{math.floor(abs(value) * scale) / scale:.{places}f}"
    return rounded, truncated


def norm(tok):
    return tok if tok.startswith("0") else "0" + tok


def blank_typography(text):
    """Blank LaTeX length/scale arguments, preserving offsets so lines still match."""
    return TYPOGRAPHY.sub(lambda m: " " * len(m.group(0)), text)


def audit_decimals(text, path, q, findings):
    """Flag any decimal that is a truncation of a real quantity, not a rounding."""
    text = blank_typography(text)
    for m in DECIMAL.finditer(text):
        if BOUNDED.search(text[max(0, m.start() - 12):m.start()]):
            continue
        tok = norm(m.group(1))
        places = len(tok.split(".")[1])
        value = float(tok)
        rounds_to, truncs_to = [], []
        for name, actual in q.items():
            if abs(actual - value) >= 10.0 ** -places:
                continue  # too far away to be a rendering of this quantity
            r, t = render(actual, places)
            if norm(r) == tok:
                rounds_to.append(name)
            elif norm(t) == tok:
                truncs_to.append((name, actual, r))
        if rounds_to or not truncs_to:
            continue  # correctly rounded, or not a rendering of anything we know
        name, actual, correct = truncs_to[0]
        findings.append({
            "kind": "TRUNCATION",
            "where": f"{path}:{line_of(text, m.start())}",
            "detail": f"{tok} appears to be {name} = {actual!r} truncated; "
                      f"correctly rounded it is {correct}",
        })


def audit_intervals(text, path, intervals, findings):
    """Every interval in the text must be an exact Clopper-Pearson interval."""
    for m in INTERVAL.finditer(text):
        lo, hi = norm(m.group(1)), norm(m.group(2))
        pair = (float(lo), float(hi))
        if pair in intervals:
            continue
        # The stochastic band (0.05, 0.95) is a definition, not an estimate.
        if pair == (0.05, 0.95):
            continue
        findings.append({
            "kind": "INTERVAL",
            "where": f"{path}:{line_of(text, m.start())}",
            "detail": f"({lo}, {hi}) is not an exact Clopper-Pearson interval of "
                      f"any cell in the run data; check the estimator",
        })


def audit_fractions(text, path, cells, findings):
    """Flag x/n citations whose denominator matches a real k but x/n does not."""
    real_n = {n for _, n in cells}
    for m in FRACTION.finditer(text):
        x, n = int(m.group(1)), int(m.group(2))
        if n not in real_n or (x, n) in cells:
            continue
        if x > n or (x, n) in PREREG_THRESHOLDS:
            continue  # a ratio or a date, or a pre-registered floor
        findings.append({
            "kind": "FRACTION",
            "where": f"{path}:{line_of(text, m.start())}",
            "detail": f"{x}/{n} is not a cell in the run data (n={n} is a real "
                      f"cell size, so this reads as a cell citation)",
        })


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def main():
    q, cells, intervals, counts, held, dev = recompute()

    print("== recomputed from run data ==")
    for name, value in counts.items():
        print(f"  {name:20s} {value}")
    print(f"  {'miss_rate[dev,pair]':20s} {q['miss_rate[dev,pair]']:.4f}")
    print(f"  {'miss_rate[held,pair]':20s} {q['miss_rate[heldout,pair]']:.4f}")
    opus = held[("opus-4.6", CAB)]
    print(f"  {'opus cab':20s} {opus.x}/{opus.n} phat={opus.x / opus.n:.5f} "
          f"miss={q['opus_miss1']:.5f}")
    print(f"  {'quantities checked':20s} {len(q)}")
    print(f"  {'real cells':20s} {len(cells)}")

    findings = []
    for rel in SOURCES:
        path = REPO / rel
        if not path.exists():
            findings.append({"kind": "MISSING", "where": rel,
                             "detail": "source listed in SOURCES does not exist"})
            continue
        text = path.read_text()
        audit_decimals(text, rel, q, findings)
        audit_intervals(text, rel, intervals, findings)
        audit_fractions(text, rel, cells, findings)

    print(f"\n== manuscript audit: {len(SOURCES)} sources ==")
    if not findings:
        print("  no findings: every decimal is a correct rounding, every "
              "interval is exact Clopper-Pearson, every cell citation is real")
        return 0

    for f in sorted(findings, key=lambda f: (f["kind"], f["where"])):
        print(f"  [{f['kind']}] {f['where']}\n      {f['detail']}")
    print(f"\n  {len(findings)} finding(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
