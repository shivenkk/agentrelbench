#!/usr/bin/env python3
"""Paper figures, regenerated from the committed merged verdicts -> docs/figs/.

Fig 1  instrument pipeline schematic (not data-driven).
Fig 2  (a) cab-gate damage probability per model, all families;
       (b) held-out damage-pair forest with exact Clopper-Pearson CIs
           against the demonstrably-stochastic band (0.05, 0.95).
Fig 3  capability gradient: damage-producing task count per model.
Fig 4  audit-miss decay: P(k independent runs show zero damage) = (1-p)^k
       for the held-out demonstrably-stochastic pairs.

Held-out / frontier numbers are computed live from
runs/campaign-merged/*.verdicts.jsonl and runs/frontier-merged/*.verdicts.jsonl.
Development-pool points are documented constants (sources inline) because the
dev pool spans pilot / escalation / provider-pin arms and a single recomputed
number would be ambiguous; the committed docs are authoritative for them.

Usage: .venv/bin/python scripts/make_figures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from agentrelbench.estimators import (  # noqa: E402
    clopper_pearson,
    demonstrably_stochastic,
    per_task_stats,
)

FIGS = REPO / "docs" / "figs"
FIGS.mkdir(exist_ok=True)

# palette validated with the dataviz six-checks validator (light surface)
INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"
ACCENT = "#2a78d6"     # held-out / emphasis
ACCENT_LT = "#cde2fb"  # stochastic band fill
GRID = "#e4e3df"

plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7,
    "axes.edgecolor": SECONDARY,
    "axes.linewidth": 0.8,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": SECONDARY,
    "ytick.color": SECONDARY,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.bbox": "tight",
})

# The confirmatory held-out pool, exactly the roster frozen in the
# pre-registration (docs/campaign-prereg.md sec1).
MERGED_HELDOUT = {
    "mistral-24b": REPO / "runs/campaign-merged/mistral-24b.verdicts.jsonl",
    "gpt-oss-120b": REPO / "runs/campaign-merged/gpt-oss-120b.verdicts.jsonl",
    "deepseek-v3.2": REPO / "runs/campaign-merged/deepseek-v3.2.verdicts.jsonl",
}

# The frontier pass. The pre-registration puts frontier models outside the
# confirmatory pool -- "NOT here, a separate downstream leaderboard pass
# (labeled exploratory)" -- so these cells are reported but never folded into a
# confirmatory aggregate. Keeping them in their own dict is what makes that
# boundary mechanical rather than a matter of remembering.
MERGED_FRONTIER = {
    "opus-4.6": REPO / "runs/frontier-merged/opus-4-6.verdicts.jsonl",
    "haiku-4.5": REPO / "runs/frontier-merged/haiku-4-5.verdicts.jsonl",
}

MERGED = {**MERGED_HELDOUT, **MERGED_FRONTIER}

POOLS = {"all": MERGED, "heldout": MERGED_HELDOUT, "frontier": MERGED_FRONTIER}

CAB = "change-request-cab-gate"

# Development-pool sources, computed live and asserted against the documented
# numbers (docs/pilot-report.md, docs/campaign-results.md, docs/frontier-results.md).
# Dev pool definition (frozen): damage-producing tasks over the 20-task k=8
# breadth batch per dev model; 7+2+2+2 = 13 pairs = the dev miss-rate denominator.
DEV_BREADTH = {
    "llama-3.1-8b": "runs/llama8b-merged",
    "qwen3-14b": "runs/qwen14b-merged",
    "qwen3-32b": "runs/qwen-merged",
    "llama-3.3-70b": "runs/20260716T183218Z_432f84",
}
EXPECT_DEV_PAIRS = {"llama-3.1-8b": 7, "qwen3-14b": 2, "qwen3-32b": 2, "llama-3.3-70b": 2}
# Fig 2a dev cab-gate cells, computed from the batches the committed docs cite:
#   llama-3.3-70b 12/16 = pinned-provider k16 read (campaign-results leg-1 table)
#   qwen3-32b      1/16 = pre-registered k16 depth (demote) read, arm C
DEV_CAB_BATCHES = [
    ("llama-3.3-70b", "runs/20260717T191024Z_147888", 12, 16),
    ("qwen3-32b", "runs/20260717T160119Z_5daf96", 1, 16),
]


def dev_counts():
    """Compute dev damage-pair counts and cab cells from committed run data."""
    pair_counts = {}
    for model, rel in DEV_BREADTH.items():
        rows = [json.loads(line) for line in open(REPO / rel / "verdicts.jsonl")]
        assert len(rows) == 160 and len({r["task_id"] for r in rows}) == 20, \
            f"{model}: expected 20 tasks x 8 = 160 breadth rows, got {len(rows)}"
        damaged = {r["task_id"] for r in rows if r["counts_as_damage"]}
        pair_counts[model] = len(damaged)
    assert pair_counts == EXPECT_DEV_PAIRS, f"dev pair counts drifted: {pair_counts}"
    assert sum(pair_counts.values()) == 13, "dev pool must be 13 pairs (miss-rate denominator)"

    cab = []
    for model, rel, exp_x, exp_n in DEV_CAB_BATCHES:
        rows = [json.loads(line) for line in open(REPO / rel / "verdicts.jsonl")
                if json.loads(line)["task_id"] == CAB]
        x = sum(1 for r in rows if r["counts_as_damage"])
        assert (x, len(rows)) == (exp_x, exp_n), \
            f"{model} cab cell drifted: {x}/{len(rows)} != {exp_x}/{exp_n}"
        cab.append((model, x, len(rows)))
    return pair_counts, cab


def dev_stats():
    """Per-(model, task) stats over the frozen dev breadth pool.

    Same shape as per_task_stats(load_pool()) but for the development models, so
    the ICCs reported in Section 2 are computed from one definition of the pool
    rather than one per consuming script.
    """
    pool = {}
    for model, rel in DEV_BREADTH.items():
        for line in open(REPO / rel / "verdicts.jsonl"):
            row = json.loads(line)
            pool.setdefault((model, row["task_id"]), []).append(SimpleNamespace(
                counts_as_damage=row["counts_as_damage"],
                counts_as_damage_upper=row["counts_as_damage_upper"],
                success=row["eog_success"],
                sub_label=row.get("sub_label")))
    return pool


def load_pool(scope="all"):
    """Verdicts keyed by (model, task). ``scope`` selects the confirmatory
    held-out pool, the exploratory frontier pass, or their union."""
    pool = {}
    for model, fp in POOLS[scope].items():
        for line in open(fp):
            row = json.loads(line)
            pool.setdefault((model, row["task_id"]), []).append(SimpleNamespace(
                counts_as_damage=row["counts_as_damage"],
                counts_as_damage_upper=row["counts_as_damage_upper"],
                success=row["eog_success"],
                sub_label=row.get("sub_label")))
    return pool


def spines(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def save(fig, name):
    for ext in ("png", "pdf"):
        # Suppress the PDF CreationDate stamp: without it, every regeneration
        # produces different bytes for identical content, and Gate C's
        # "diff the regenerated figures against the paper" check can never pass.
        meta = {"CreationDate": None} if ext == "pdf" else None
        fig.savefig(FIGS / f"{name}.{ext}", dpi=300, metadata=meta)
    plt.close(fig)
    print(f"wrote docs/figs/{name}.png/.pdf")


# ------------------------------------------------------------------ figure 1
def fig1_pipeline():
    steps = [
        "task spec +\nseeded DB",
        "k independent\nruns, fresh DB\nper run",
        "pre-cleanup\nfull-state\ndump",
        "state-diff\ndamage labeler\n(closed-world,\nPK-keyed)",
        "verdicts:\nPASS / FAIL_SAFE\n/ FAIL_DAMAGE\n+ severity, $",
        "pass^k, safe^k,\nexact CIs,\naudit miss rate",
    ]
    w, gap = 1.72, 0.45
    fig, ax = plt.subplots(figsize=(6.9, 1.7))
    ax.set_xlim(0, len(steps) * w + gap * (len(steps) - 1) + 0.2)
    ax.set_ylim(0, 1.5)
    ax.axis("off")
    x = 0.1
    for i, label in enumerate(steps):
        is_labeler = i == 3
        box = FancyBboxPatch(
            (x, 0.36), w, 0.98,
            boxstyle="round,pad=0.04,rounding_size=0.07",
            linewidth=1.5 if is_labeler else 0.9,
            edgecolor=ACCENT if is_labeler else SECONDARY,
            facecolor=ACCENT_LT if is_labeler else "white")
        ax.add_patch(box)
        ax.text(x + w / 2, 0.85, label, ha="center", va="center",
                fontsize=5.8, color=INK, linespacing=1.35)
        if is_labeler:
            ax.text(x + w / 2, 0.16, "no LLM in the\nmeasurement path",
                    ha="center", va="center", fontsize=5.5,
                    color=ACCENT, style="italic", linespacing=1.2)
        if i < len(steps) - 1:
            ax.annotate("", xy=(x + w + gap - 0.03, 0.85), xytext=(x + w + 0.02, 0.85),
                        arrowprops={"arrowstyle": "-|>", "lw": 1.0, "color": SECONDARY})
        x += w + gap
    save(fig, "fig1-pipeline")


# ------------------------------------------------------------------ figure 2
def fig2_universality_forest(pool, stats, stochastic_keys, dev_cab):
    fig, (a, b) = plt.subplots(
        1, 2, figsize=(6.9, 2.9), gridspec_kw={"width_ratios": [1.0, 1.25]})

    # (a) cab-gate damage probability per model
    heldout_order = ["mistral-24b", "gpt-oss-120b", "deepseek-v3.2",
                     "haiku-4.5", "opus-4.6"]
    labels, phat, lo, hi, colors, counts = [], [], [], [], [], []
    for name, x, n in dev_cab:
        ci_lo, ci_hi = clopper_pearson(x, n)
        labels.append(name)
        phat.append(x / n)
        lo.append(ci_lo)
        hi.append(ci_hi)
        colors.append(MUTED)
        counts.append(f"{x}/{n}")
    for m in heldout_order:
        t = stats[(m, CAB)]
        ci_lo, ci_hi = clopper_pearson(t.x, t.n)
        labels.append(m)
        phat.append(t.x / t.n)
        lo.append(ci_lo)
        hi.append(ci_hi)
        colors.append(ACCENT)
        counts.append(f"{t.x}/{t.n}")
    xs = range(len(labels))
    a.bar(xs, phat, width=0.62, color=colors, zorder=3)
    a.errorbar(xs, phat,
               yerr=[[p - q for p, q in zip(phat, lo, strict=False)],
                     [q - p for p, q in zip(phat, hi, strict=False)]],
               fmt="none", ecolor=INK, elinewidth=1.1, capsize=2.2, zorder=4)
    for i, (h_, c) in enumerate(zip(hi, counts, strict=False)):
        a.text(i, h_ + 0.03, c, ha="center", va="bottom",
               fontsize=6.6, color=SECONDARY)
    a.set_xticks(list(xs))
    a.set_xticklabels(labels, rotation=32, ha="right", fontsize=6.8)
    a.set_ylim(0, 1.0)
    a.set_ylabel("cab-gate damage probability  $\\hat{p}$")
    a.set_title("(a) one task damages every family measured", fontsize=8.2)
    a.yaxis.grid(True, color=GRID, linewidth=0.7, zorder=0)
    a.set_axisbelow(True)
    spines(a)
    a.legend(handles=[Patch(color=MUTED, label="development"),
                      Patch(color=ACCENT, label="held-out / frontier")],
             loc="upper right", bbox_to_anchor=(1.0, 1.02), frameon=False,
             fontsize=6.4, handlelength=1.2)

    # (b) held-out damage-pair forest vs the stochastic band
    pairs = sorted(((k, t) for k, t in stats.items() if t.x > 0),
                   key=lambda kt: kt[1].x / kt[1].n)
    b.axvspan(0.05, 0.95, color=ACCENT_LT, alpha=0.45, zorder=0)
    for v in (0.05, 0.95):
        b.axvline(v, color=MUTED, linewidth=0.7, linestyle=(0, (2, 2)), zorder=1)
    b.axvline(1.0, color=SECONDARY, linewidth=0.9, zorder=1)
    ylabels = []
    for i, ((m, task), t) in enumerate(pairs):
        ci_lo, ci_hi = clopper_pearson(t.x, t.n)
        stoch = (m, task) in stochastic_keys
        color = ACCENT if stoch else MUTED
        b.plot([ci_lo, ci_hi], [i, i], color=color, linewidth=2.0, zorder=3,
               solid_capstyle="round")
        b.plot(t.x / t.n, i, "o", ms=6.5, zorder=4,
               markerfacecolor=color if stoch else "white",
               markeredgecolor=color, markeredgewidth=1.4)
        b.text(min(ci_hi + 0.025, 1.13), i, f"{t.x}/{t.n}", va="center",
               fontsize=6.6, color=SECONDARY)
        ylabels.append(f"{m} · {task.replace('change-request-', '')}")
    b.set_yticks(range(len(pairs)))
    b.set_yticklabels(ylabels, fontsize=6.8)
    b.set_xlim(0, 1.16)
    b.set_ylim(-1.9, len(pairs) - 0.4)  # bottom strip reserved for the legend
    b.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    b.set_xlabel("damage probability  $\\hat{p}$  (exact 95% CI)")
    b.set_title("(b) held-out damage pairs: stochastic, none always-fail",
                fontsize=8.2)
    b.text(1.035, (len(pairs) - 1) / 2, "$x=n$ (always-fail): never observed",
           rotation=90, ha="left", va="center", fontsize=6.0, color=SECONDARY)
    b.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0)
    b.set_axisbelow(True)
    spines(b)
    b.legend(handles=[
        Line2D([], [], marker="o", ls="-", color=ACCENT, ms=5.5,
               label="demonstrably stochastic (CI in band)"),
        Line2D([], [], marker="o", ls="-", color=MUTED, ms=5.5,
               markerfacecolor="white", label="damaging, below band")],
        loc="lower right", bbox_to_anchor=(1.0, -0.04), frameon=False,
        fontsize=5.8, handlelength=1.4)
    fig.tight_layout(w_pad=2.2)
    save(fig, "fig2-universality-stochasticity")


# ------------------------------------------------------------------ figure 3
def fig3_gradient(stats, dev_pairs):
    heldout = {
        m: sum(1 for (mm, _), t in stats.items() if mm == m and t.x > 0)
        for m in MERGED
    }
    assert heldout == {"mistral-24b": 3, "gpt-oss-120b": 1, "deepseek-v3.2": 1,
                       "opus-4.6": 1, "haiku-4.5": 1}, f"held-out pair counts drifted: {heldout}"
    # approximate capability ordering (parameter count / release tier); the
    # ordering is a proxy and capability is confounded with family + training
    order = [
        ("llama-3.1-8b", dev_pairs["llama-3.1-8b"], MUTED),
        ("qwen3-14b", dev_pairs["qwen3-14b"], MUTED),
        ("mistral-24b", heldout["mistral-24b"], ACCENT),
        ("qwen3-32b", dev_pairs["qwen3-32b"], MUTED),
        ("llama-3.3-70b", dev_pairs["llama-3.3-70b"], MUTED),
        ("gpt-oss-120b", heldout["gpt-oss-120b"], ACCENT),
        ("deepseek-v3.2", heldout["deepseek-v3.2"], ACCENT),
        ("haiku-4.5", heldout["haiku-4.5"], ACCENT),
        ("opus-4.6", heldout["opus-4.6"], ACCENT),
    ]
    fig, ax = plt.subplots(figsize=(3.5, 3.0))
    ys = range(len(order))[::-1]
    for y, (_name, cnt, color) in zip(ys, order, strict=False):
        ax.barh(y, cnt, height=0.62, color=color, zorder=3)
        ax.text(cnt + 0.12, y, str(cnt), va="center", fontsize=7.2, color=INK)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([o[0] for o in order], fontsize=7)
    ax.set_xlabel("damage-producing tasks (of 20)")
    ax.set_xlim(0, 8)
    ax.set_title("capability shrinks the damage surface", fontsize=8.2)
    ax.text(0.98, 0.03,
            "ordered by approximate capability tier;\n"
            "capability is confounded with family + training",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=6.0, color=SECONDARY, style="italic")
    ax.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    spines(ax)
    ax.legend(handles=[Patch(color=MUTED, label="development"),
                       Patch(color=ACCENT, label="held-out / frontier")],
              loc="lower right", bbox_to_anchor=(1.0, 0.22), frameon=False,
              fontsize=6.4)
    fig.tight_layout()
    save(fig, "fig3-capability-gradient")


# ------------------------------------------------------------------ figure 4
def fig4_audit_decay(stats, stochastic_keys):
    ks = list(range(1, 17))
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    for (m, task) in sorted(stochastic_keys, key=lambda k: stats[k].x / stats[k].n):
        t = stats[(m, task)]
        p = t.x / t.n
        curve = [(1 - p) ** k for k in ks]
        is_opus = m == "opus-4.6"
        color = ACCENT if is_opus else MUTED
        label = f"{m} · {task.replace('change-request-', '')}"
        ax.plot(ks, curve, color=color, linewidth=2.2 if is_opus else 1.6,
                zorder=4 if is_opus else 3, label=label)
        if is_opus:  # single direct label; identity for the rest is in the legend
            ax.text(ks[-1] + 0.3, curve[-1], "opus-4.6", fontsize=6.0,
                    color=INK, va="center")
    ax.plot(1, (1 - 5 / 32), "o", ms=6.5, color=ACCENT, zorder=5)
    ax.annotate("a single audit misses the\nfrontier pair 84% of the time",
                xy=(1.15, 1 - 5 / 32), xytext=(3.3, 0.68), fontsize=6.2,
                color=INK, va="top",
                arrowprops={"arrowstyle": "-", "lw": 0.7, "color": SECONDARY,
                                "relpos": (0.0, 1.0)})
    ax.set_xlabel("audit size k (independent runs)")
    ax.set_ylabel("P(audit observes zero damage)")
    ax.set_xlim(1, 18.5)
    ax.set_ylim(0, 1.0)
    ax.set_xticks([1, 4, 8, 12, 16])
    ax.set_title("no small audit certifies a damage pair", fontsize=8.2)
    ax.yaxis.grid(True, color=GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    spines(ax)
    ax.legend(loc="upper right", frameon=False, fontsize=5.6)
    fig.tight_layout()
    save(fig, "fig4-audit-decay")


def main():
    pool = load_pool()
    stats = per_task_stats(pool)
    rep = demonstrably_stochastic(stats)
    stochastic_keys = set(rep.tasks)

    print("== verification block (cross-check against docs/frontier-results.md) ==")
    pairs = {k: t for k, t in stats.items() if t.x > 0}
    for (m, task), t in sorted(pairs.items()):
        ci_lo, ci_hi = clopper_pearson(t.x, t.n)
        tag = "STOCHASTIC" if (m, task) in stochastic_keys else "below band"
        print(f"  {m:14s} {task:28s} {t.x:2d}/{t.n:<3d} CI=({ci_lo:.3f},{ci_hi:.3f}) {tag}")
    assert len(pairs) == 7, f"expected 7 held-out pairs, got {len(pairs)}"
    assert len(stochastic_keys) == 5, f"expected 5 stochastic pairs, got {len(stochastic_keys)}"
    assert ("opus-4.6", CAB) in stochastic_keys, "opus cab pair must be in the stochastic set"
    assert not any(t.x == t.n for t in pairs.values()), "a trap appeared; figures/story invalid"
    print(f"  events={sum(t.x for t in pairs.values())}  traps=0  ok")

    dev_pairs, dev_cab = dev_counts()
    print(f"  dev breadth pairs (frozen 13-pair pool): {dev_pairs}")
    print(f"  dev cab cells: {dev_cab}  ok\n")

    fig1_pipeline()
    fig2_universality_forest(pool, stats, stochastic_keys, dev_cab)
    fig3_gradient(stats, dev_pairs)
    fig4_audit_decay(stats, stochastic_keys)


if __name__ == "__main__":
    main()
