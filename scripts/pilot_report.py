#!/usr/bin/env python3
"""Pilot report generator: verdicts × predictions × estimators → markdown.

Usage:
    .venv/bin/python scripts/pilot_report.py \
        --batch <model_name>=<runs/batch_dir> [--batch <model2>=<dir2> ...] \
        --tasks tasks/ --out docs/pilot-report.md

Per model it computes the per-task p̂ table (with exact Clopper–Pearson CIs),
the predicted-vs-actual lever comparison (Shiven's explicit ask, 2026-07-16),
pass^k / safe^k curves, the k=1 audit miss rate, damage-mass share, the
demonstrably-stochastic set, and the beta-binomial decomposition. Analysis
lives in the tested estimators module; this script only joins and formats.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentrelbench.estimators import (  # noqa: E402
    audit_miss_rate,
    cluster_bootstrap,
    damage_mass_share,
    demonstrably_stochastic,
    fit_beta_binomial,
    pass_pow_k,
    per_task_stats,
    phat_distribution,
    safe_pow_k,
)


def load_verdicts(batch_dir: Path) -> dict:
    """verdicts.jsonl → {task_id: [verdict-like objects]}."""
    by_task: dict = {}
    with open(batch_dir / "verdicts.jsonl") as f:
        for line in f:
            row = json.loads(line)
            by_task.setdefault(row["task_id"], []).append(
                SimpleNamespace(
                    counts_as_damage=row["counts_as_damage"],
                    counts_as_damage_upper=row["counts_as_damage_upper"],
                    success=row["eog_success"],
                    sub_label=row.get("sub_label"),
                )
            )
    return by_task


def load_predictions(tasks_root: Path) -> dict:
    """{task_dir_name: predicted_lever block} from every damage.json."""
    out = {}
    for damage_path in sorted(tasks_root.rglob("damage.json")):
        block = json.loads(damage_path.read_text()).get("predicted_lever", {})
        out[damage_path.parent.name] = block
    return out


def actual_region(phat: float, ci_lo: float, ci_hi: float) -> str:
    """Point-estimate region with the same eps conventions as the estimators
    (0.05 boundaries); the CI-based demonstrably-stochastic flag is reported
    separately and is the falsifier-grade statement."""
    if phat <= 0.05:
        return "near_zero"
    if phat >= 0.95:
        return "near_one"
    return "intermediate"


def fmt(x, nd=3):
    return "—" if x is None else f"{x:.{nd}f}"


def report_model(model: str, batch_dir: Path, predictions: dict) -> str:
    stats = per_task_stats(load_verdicts(batch_dir))
    phats = phat_distribution(stats)
    stoch = demonstrably_stochastic(stats)
    lines = [f"## Model: {model}", "", f"Batch: `{batch_dir}`", ""]

    # --- per-task p̂ table + predicted-vs-actual ---
    lines += [
        "### Per-task p̂ (damage probability) — predicted vs. actual",
        "",
        "| task | n | damage runs | p̂ | 95% CI | pass runs | lever (predicted) | predicted region | actual region | match | demonstrably stochastic |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    matches = mismatches = 0
    for task in sorted(stats):
        t, p = stats[task], phats[task]
        pred = predictions.get(task, {})
        pred_region = pred.get("predicted_phat_region", "?")
        act = actual_region(p.phat, p.ci_lo, p.ci_hi)
        ok = "✓" if pred_region == act else "✗"
        matches += pred_region == act
        mismatches += pred_region != act
        lines.append(
            f"| {task} | {t.n} | {t.x} | {p.phat:.2f} | ({p.ci_lo:.2f}, {p.ci_hi:.2f}) | {t.s} "
            f"| {pred.get('lever', '?')} | {pred_region} | {act} | {ok} | {'YES' if task in stoch.tasks else ''} |"
        )
    lines += [
        "",
        f"Predicted-vs-actual: **{matches} match / {mismatches} mismatch** "
        f"(an inert batch shows as systematic intermediate→near_zero mismatches).",
        "",
    ]

    # --- aggregates ---
    n_min = min(t.n for t in stats.values())
    pass_curve = {k: pass_pow_k(stats, k).value for k in range(1, n_min + 1)}
    safe_curve = {k: safe_pow_k(stats, k).value for k in range(1, n_min + 1)}
    safe_upper = {k: safe_pow_k(stats, k, upper=True).value for k in range(1, n_min + 1)}
    lines += [
        "### Reliability curves",
        "",
        "| k | pass^k | safe^k | safe^k (upper bound) |",
        "|---|---|---|---|",
    ]
    for k in pass_curve:
        lines.append(f"| {k} | {pass_curve[k]:.3f} | {safe_curve[k]:.3f} | {safe_upper[k]:.3f} |")
    lines.append("")

    # --- headline statistics ---
    try:
        miss_pair = audit_miss_rate(stats, weighting="pair")
        miss_event = audit_miss_rate(stats, weighting="event")
        miss_ci = cluster_bootstrap(lambda s: audit_miss_rate(s, weighting="pair"), stats, n_boot=5000, seed=7)
        miss_line = (
            f"- **k=1 audit miss rate**: pair-weighted {miss_pair:.3f} "
            f"(bootstrap 95% CI {miss_ci[0]:.3f}–{miss_ci[1]:.3f}), event-weighted {miss_event:.3f}"
        )
    except ValueError:
        miss_line = "- **k=1 audit miss rate**: undefined — zero damage-producing tasks (inert batch for this model)"
    bb = fit_beta_binomial(stats)
    lines += [
        "### Headline statistics",
        "",
        miss_line,
        f"- **Damage-mass share at intermediate p̂** (ε=0.1): {damage_mass_share(stats, eps=0.1):.3f} "
        f"(ε=0.05: {damage_mass_share(stats, eps=0.05):.3f}, ε=0.2: {damage_mass_share(stats, eps=0.2):.3f})",
        f"- **Demonstrably-stochastic tasks** (CI ⊂ (0.05, 0.95)): {len(stoch.tasks)} "
        f"carrying {stoch.damage_share:.3f} of damage events: {sorted(stoch.tasks) if stoch.tasks else '—'}",
        f"- **Beta-binomial**: ICC={bb.icc:.3f}, overdispersion p={bb.overdispersion_pvalue:.4f}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", action="append", required=True, metavar="MODEL=BATCH_DIR")
    ap.add_argument("--tasks", default="tasks", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    predictions = load_predictions(args.tasks)
    sections = ["# Pilot report — per-task p̂ distribution & predicted-vs-actual levers", ""]
    for spec in args.batch:
        model, _, batch = spec.partition("=")
        sections.append(report_model(model, Path(batch), predictions))
    text = "\n".join(sections)
    if args.out:
        args.out.write_text(text)
        print(f"written: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
