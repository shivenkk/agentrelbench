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

import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from make_figures import (  # noqa: E402
    CAB,
    dev_stats,
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
    # The README is a public artifact that quotes headline numbers, so it gets
    # the same drift gate as the paper.
    "README.md",
]

DECIMAL = re.compile(r"(?<![\d.])(0?\.\d{2,4})(?![\d])")
INTERVAL = re.compile(r"\(\s*(0?\.\d{2,4})\s*,\s*(0?\.\d{2,4})\s*\)")
FRACTION = re.compile(r"(?<![\d./])(\d{1,3})\s*/\s*(\d{1,3})(?![\d/])")
PERCENT = re.compile(
    r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(?:\\%|%)(?![0-9A-Fa-f]{2})")

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

# Percentages that state a convention rather than report a measurement: the
# confidence level, and the stochastic band edge. Both are chosen, not computed.
DEFINITIONAL_PERCENTS = {
    95.0,   # confidence level
    5.0,    # stochastic band edge
    50.0,   # coin-flip reference
    20.0,   # pre-registered errored-run ceiling above which a cell is invalid
}

# Errored runs, as the labeler's sub-labels record them. The pre-registration
# invalidates a cell with more than 20% of these (docs/campaign-prereg.md sec4).
ERRORED_SUB_LABELS = {"errored_after_mutation", "errored_clean"}

# A decimal introduced by an inequality is a bound, not a point estimate:
# "p < 0.001" is a threshold the data clears, and comparing it against nearby
# quantities produces spurious truncation findings.
BOUNDED = re.compile(r"(?:[<>]|\\l[et]q?|\\g[et]q?|\\ll|\\gg)\s*\$?\s*$")


def recompute():
    """Every derived quantity the manuscript could cite, computed from run data.

    Returns (quantities, cells, intervals) where quantities maps a name to a
    float, cells is the set of real (x, n) pairs, and intervals is the set of
    exact Clopper-Pearson (lo, hi) pairs.
    """
    # "heldout" is the confirmatory pool only. The pre-registration places the
    # frontier pass outside it ("a separate downstream leaderboard pass (labeled
    # exploratory)"), so frontier cells are recomputed under their own label and
    # never enter a confirmatory aggregate.
    held = per_task_stats(load_pool("heldout"))
    frontier = per_task_stats(load_pool("frontier"))
    dev = per_task_stats(dev_stats())

    q, cells, intervals = {}, set(), set()

    for label, stats in (("heldout", held), ("frontier", frontier), ("dev", dev)):
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
    # Section 2 states this one over the pooled held-out AND frontier cells and
    # says so in the sentence, so the pooled fit is what gets audited there.
    producing_held = {k: v for k, v in held.items() if v.x > 0}
    for label, stats in (("heldout+frontier", {**held, **frontier}), ("dev", dev)):
        q[f"icc[{label},all]"] = fit_beta_binomial(stats).icc
        producing = {k: v for k, v in stats.items() if v.x > 0}
        if len(producing) > 1:
            fit = fit_beta_binomial(producing)
            q[f"icc[{label},damage-producing]"] = fit.icc
            # The unfloored value is cited in Section 2 to explain why a reported
            # ICC of exactly 0.000 is a floored estimate and not a bug.
            q[f"icc_raw[{label},damage-producing]"] = abs(fit.icc_raw)

    # Exact one-sided 95% upper limits on trap prevalence given zero traps
    # observed, cited in Section 5.1. One-sided because the claim is
    # directional; the rule-of-three approximation 3/n is wrong by 8pp at n=7.
    for label, n in (("damage-producing cells", len(producing_held)),
                     ("all held-out cells", len(held))):
        q[f"trap_upper_1sided[{label}]"] = 1.0 - 0.05 ** (1.0 / n)

    q["miss_rate[dev,pair]"] = audit_miss_rate(dev, "pair")
    q["miss_rate[dev,event]"] = audit_miss_rate(dev, "event")
    q["miss_rate[heldout,pair]"] = audit_miss_rate(held, "pair")
    q["miss_rate[heldout,event]"] = audit_miss_rate(held, "event")
    q["miss_rate[frontier,pair]"] = audit_miss_rate(frontier, "pair")

    # Errored-ceiling sensitivity, cited in Section 5.1. The pre-registration
    # invalidates any cell with more than 20% errored runs; two held-out cells
    # breach it and are retained with disclosure, which LOWERS the headline, so
    # the excluding value is reported alongside it.
    breaching = set()
    for scope in ("heldout", "frontier"):
        for key, runs in load_pool(scope).items():
            errored = sum(1 for v in runs if v.sub_label in ERRORED_SUB_LABELS)
            if not errored:
                continue
            # Section 5.1 cites these as x/n counts, so they are real cells.
            q[f"errored[{scope}/{key[0]}/{key[1]}]"] = errored / len(runs)
            cells.add((errored, len(runs)))
            if scope == "heldout" and errored / len(runs) > 0.20:
                breaching.add(key)
    q["miss_rate[heldout-excl-breaching,pair]"] = audit_miss_rate(
        {k: v for k, v in held.items() if k not in breaching}, "pair")

    # Audit-decay figures: the paper reports (1 - p)^k for the opus cab cell.
    opus = frontier[("opus-4.6", CAB)]
    miss = (opus.n - opus.x) / opus.n
    q["opus_miss1"] = miss
    for k in (2, 3, 4, 5, 8, 16, 18):
        q[f"decay[opus,k={k}]"] = miss ** k

    counts = {
        "heldout_cells": len(held),
        "heldout_pairs": sum(1 for t in held.values() if t.x > 0),
        "heldout_events": sum(t.x for t in held.values()),
        "heldout_stochastic": len(demonstrably_stochastic(held).tasks),
        "heldout_stoch_models": len({m for m, _ in demonstrably_stochastic(held).tasks}),
        "heldout_traps": sum(1 for t in held.values() if t.x == t.n and t.n),
        "frontier_cells": len(frontier),
        "frontier_pairs": sum(1 for t in frontier.values() if t.x > 0),
        "frontier_events": sum(t.x for t in frontier.values()),
        "frontier_stochastic": len(demonstrably_stochastic(frontier).tasks),
        "dev_pairs": sum(1 for t in dev.values() if t.x > 0),
        "dev_events": sum(t.x for t in dev.values()),
    }
    return q, cells, intervals, counts, frontier, dev


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


# ---------------------------------------------------------------- anchored claims
#
# Set membership is a weak contract. With ~100 recomputed quantities, 39% of all
# integer percentages and 4.8% of one-decimal values match *something*, so a
# drifted headline number can stay hidden behind an unrelated coincidence. The
# rule-of-three error this gate was built to catch did exactly that: 43% passed
# because decay[opus,k=5] happens to be 42.763%.
#
# For claims the paper's argument rests on, bind the number to the quantity it is
# supposed to be. Each entry is (label, context pattern, quantity name, decimals);
# the pattern's single group must capture the number as written.
ANCHORED = [
    ("trap bound, damage-producing cells",
     r"one-sided 95% upper limit of ([\d.]+)%",
     "trap_upper_1sided[damage-producing cells]", 1),
    ("trap bound, all held-out cells",
     r"across all 60 confirmatory held-out cells the limit is ([\d.]+)%",
     "trap_upper_1sided[all held-out cells]", 1),
    ("k=1 audit miss rate, development pool (pre-registered primary)",
     r"pair ([\d.]+) of the time on the development pool",
     "miss_rate[dev,pair]", 2),
    ("k=1 audit miss rate, confirmatory held-out pool",
     r"held-out pool gives ([\d.]+) over 5 pairs",
     "miss_rate[heldout,pair]", 3),
    # The errored-ceiling sensitivity moves the headline UP, so it is exactly the
    # number a reader must be able to check against the data.
    ("k=1 audit miss rate, excluding the ceiling-breaching held-out cells",
     r"miss rate to ([\d.]+) over the four remaining pairs",
     "miss_rate[heldout-excl-breaching,pair]", 3),
    # Leg 2's miss-rate conjunct is ambiguous in the frozen wording ("pooled ...
    # over the held-out damage-producing pairs"), and the two readings straddle
    # the 0.5 threshold. Both are reported, so both are anchored: the one that
    # clears must not drift, and neither must the one that does not.
    ("k=1 audit miss rate, pair-weighted (leg-2 conjunct, primary reading)",
     r"pair equally gives ([\d.]+), which clears",
     "miss_rate[heldout,pair]", 3),
    ("k=1 audit miss rate, event-weighted (leg-2 conjunct, alternate reading)",
     r"damage events it carries gives ([\d.]+), which does not",
     "miss_rate[heldout,event]", 3),
    ("k=1 audit miss rate, pair-weighted (Appendix F restatement)",
     r"pair-weighted it is ([\d.]+) and clears",
     "miss_rate[heldout,pair]", 3),
    ("k=1 audit miss rate, event-weighted (Appendix F restatement)",
     r"event-weighted it is ([\d.]+) and does not",
     "miss_rate[heldout,event]", 3),
    # The README states the same pair on its own phrasing, and it is the most
    # widely read of these surfaces, so it gets its own anchors rather than
    # relying on the decimal scan.
    ("k=1 audit miss rate, pair-weighted (README)",
     r"([\d.]+) over 5 confirmatory held-out pairs",
     "miss_rate[heldout,pair]", 3),
    ("k=1 audit miss rate, event-weighted (README)",
     r"event-weighted the same quantity is ([\d.]+)",
     "miss_rate[heldout,event]", 3),
    ("frontier single-audit miss",
     r"single audit misses it ([\d.]+)% of the time",
     "opus_miss1", 0),
]

# LaTeX and markdown write the same sentence differently; normalize before matching.
def normalize(text):
    text = re.sub(r"\\(?:phat|passk|safek)\{?\}?", "p-hat", text)
    text = text.replace("\\%", "%").replace("$", "").replace("~", " ")
    text = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"[{}]", "", text)
    return re.sub(r"\s+", " ", text)


def audit_anchored(text, path, q, findings):
    """Each headline number must equal the specific quantity it claims to be."""
    norm = normalize(text)
    for label, pattern, name, places in ANCHORED:
        for m in re.finditer(pattern, norm):
            written = m.group(1)
            if name not in q:
                findings.append({"kind": "ANCHOR", "where": path,
                                 "detail": f"{label}: quantity {name!r} is not recomputed"})
                continue
            actual = q[name]
            scale = 100 if "%" in pattern else 1
            expect = f"{actual * scale:.{places}f}"
            if written != expect:
                findings.append({
                    "kind": "ANCHOR",
                    "where": path,
                    "detail": (f"{label}: text says {written} but {name} = "
                               f"{actual * scale:.4f} (expected {expect})"),
                })


def audit_percents(text, path, q, findings):
    """A percentage in the text must round to some recomputed quantity.

    Percentages were previously unaudited, so the 84% frontier audit-miss figure
    and the trap-prevalence bounds sat outside the gate entirely.
    """
    for m in PERCENT.finditer(text):
        value = float(m.group(1))
        if value in DEFINITIONAL_PERCENTS:
            continue
        places = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
        matches = [name for name, actual in q.items()
                   if f"{actual * 100:.{places}f}" == m.group(1)]
        if matches:
            continue
        near = sorted(((abs(actual * 100 - value), name, actual * 100)
                       for name, actual in q.items()), key=lambda z: z[0])[:1]
        hint = f"; nearest recomputed value is {near[0][1]} = {near[0][2]:.2f}%" if near else ""
        findings.append({
            "kind": "PERCENT",
            "where": f"{path}:{line_of(text, m.start())}",
            "detail": f"{m.group(1)}% does not round to any recomputed quantity{hint}",
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
    q, cells, intervals, counts, frontier, dev = recompute()

    print("== recomputed from run data ==")
    for name, value in counts.items():
        print(f"  {name:20s} {value}")
    print(f"  {'miss_rate[dev,pair]':20s} {q['miss_rate[dev,pair]']:.4f}")
    print(f"  {'miss_rate[held,pair]':20s} {q['miss_rate[heldout,pair]']:.4f}")
    print(f"  {'miss_rate[held,-breach]':20s} "
          f"{q['miss_rate[heldout-excl-breaching,pair]']:.4f}")
    opus = frontier[("opus-4.6", CAB)]
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
        audit_percents(text, rel, q, findings)
        audit_anchored(text, rel, q, findings)

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
