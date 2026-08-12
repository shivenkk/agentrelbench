"""Tests for the manuscript number audit (scripts/audit_numbers.py).

A verification gate that cannot fail is worse than no gate: it reports clean
forever and earns trust it has not established. These tests pin the three
failure modes the audit exists to catch, and pin the two false-positive classes
that would otherwise make it noise.

The audit's own check functions are pure (text, path, recomputed -> findings),
so they are testable without touching run data.
"""

import sys
from pathlib import Path
from typing import ClassVar

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from audit_numbers import (  # noqa: E402
    audit_decimals,
    audit_fractions,
    audit_intervals,
    audit_percents,
    blank_typography,
)

# 0.84375^5 = 0.427630752..., so 0.43 is correct and 0.42 is the truncation.
DECAY5 = 0.84375 ** 5
QUANTITIES = {"decay[opus,k=5]": DECAY5, "opus_phat": 5 / 32}

# Exact Clopper-Pearson interval for the opus cab cell, 5/32.
OPUS_CI = (0.053, 0.328)


def findings_for(fn, text, arg):
    out = []
    fn(text, "t.tex", arg, out)
    return out


class TestTruncationDetection:
    def test_truncated_decimal_is_flagged(self):
        out = findings_for(audit_decimals, "the miss decays to 0.42 by k=5",
                           QUANTITIES)
        assert len(out) == 1
        assert out[0]["kind"] == "TRUNCATION"
        assert "0.43" in out[0]["detail"]

    def test_correctly_rounded_decimal_passes(self):
        assert findings_for(audit_decimals, "the miss decays to 0.43 by k=5",
                            QUANTITIES) == []

    def test_truncation_flagged_even_beside_a_correct_sibling(self):
        """sqlpup's actual bug: one cell of a row rounds, its neighbour truncates."""
        out = findings_for(audit_decimals, "p-hat 0.156 and decay 0.42", QUANTITIES)
        assert [f["kind"] for f in out] == ["TRUNCATION"]

    def test_unrelated_decimal_is_not_flagged(self):
        assert findings_for(audit_decimals, "alpha = 0.05 throughout",
                            QUANTITIES) == []

    def test_inequality_bounds_are_not_point_estimates(self):
        """"p < 0.001" is a threshold the data clears, not a rounded quantity.
        Without this, any bound landing near a real value is flagged: the real
        case was "p < 0.001" against a CI lower bound of 0.00158."""
        q = {"ci_lo": 0.0015811117223165638}
        assert findings_for(audit_decimals, "overdispersion p < 0.001", q) == []
        assert findings_for(audit_decimals, r"$p < 0.001$ for both", q) == []
        assert findings_for(audit_decimals, r"with $p \leq 0.001$", q) == []

    def test_a_bare_truncation_is_still_caught_without_the_inequality(self):
        """The bound exemption must not swallow the case it neighbours."""
        q = {"ci_lo": 0.0015811117223165638}
        out = findings_for(audit_decimals, "the interval starts at 0.001", q)
        assert len(out) == 1 and out[0]["kind"] == "TRUNCATION"

    def test_line_number_is_reported(self):
        out = findings_for(audit_decimals, "intro\n\nthe value 0.42 here",
                           QUANTITIES)
        assert out[0]["where"] == "t.tex:3"


class TestIntervalEstimatorConsistency:
    def test_exact_clopper_pearson_interval_passes(self):
        assert findings_for(audit_intervals, "an exact CI of (0.053, 0.328)",
                            {OPUS_CI}) == []

    def test_foreign_estimator_is_flagged(self):
        """A continuity-corrected interval among exact ones: sqlpup failure mode 3."""
        out = findings_for(audit_intervals, "CI of (0.048, 0.335)", {OPUS_CI})
        assert len(out) == 1 and out[0]["kind"] == "INTERVAL"

    def test_stochastic_band_is_a_definition_not_an_estimate(self):
        assert findings_for(audit_intervals, "strictly inside (0.05, 0.95)",
                            {OPUS_CI}) == []


class TestFractionCitations:
    CELLS: ClassVar[set] = {(5, 32), (27, 32), (12, 16)}

    def test_real_cell_passes(self):
        assert findings_for(audit_fractions, "5/32 runs damaged", self.CELLS) == []

    def test_wrong_cell_with_real_denominator_is_flagged(self):
        out = findings_for(audit_fractions, "7/32 runs damaged", self.CELLS)
        assert len(out) == 1 and out[0]["kind"] == "FRACTION"

    def test_prereg_engagement_floor_is_not_a_cell(self):
        """6/32 and 3/16 are frozen thresholds, deliberately not observed cells."""
        text = "an engagement floor of 6/32 (pass >= 3/16 at k=16)"
        assert findings_for(audit_fractions, text, self.CELLS) == []

    def test_unknown_denominator_is_ignored(self):
        assert findings_for(audit_fractions, "see 3/7 of the docs", self.CELLS) == []


class TestTypographyIsNotStatistics:
    def test_latex_column_spec_is_blanked(self):
        assert "0.42" not in blank_typography(r"\begin{tabular}{@{}clp{0.42\linewidth}@{}}")

    def test_includegraphics_width_is_blanked(self):
        assert "0.85" not in blank_typography(r"\includegraphics[width=0.85\textwidth]{f}")

    def test_blanking_preserves_offsets_so_line_numbers_stay_correct(self):
        raw = r"line one" + "\n" + r"p{0.42\linewidth} and 0.42 prose"
        blanked = blank_typography(raw)
        assert len(blanked) == len(raw)
        assert blanked.count("\n") == raw.count("\n")

    def test_column_spec_decimal_does_not_reach_the_decimal_audit(self):
        text = r"\begin{tabular}{@{}clp{0.42\linewidth}@{}}"
        assert findings_for(audit_decimals, text, QUANTITIES) == []


class TestPercentages:
    """Percentages were unaudited until the trap bounds needed binding, which left
    the 84% frontier audit-miss figure outside the gate as well."""

    Q: ClassVar[dict] = {"opus_miss": 0.84375, "trap_upper": 0.34816, "band": 0.0295}

    def test_correct_percentage_passes(self):
        assert findings_for(audit_percents, "misses it 84\\% of the time", self.Q) == []

    def test_wrong_percentage_is_flagged(self):
        out = findings_for(audit_percents, "misses it 87\\% of the time", self.Q)
        assert len(out) == 1 and out[0]["kind"] == "PERCENT"
        assert "opus_miss" in out[0]["detail"]

    def test_rule_of_three_approximation_would_be_caught(self):
        """The exact one-sided limit at n=7 is 34.8%; 3/7 = 43% is the approximation
        that shipped once and had to be corrected."""
        out = findings_for(audit_percents, "upper limit near 43\\%", self.Q)
        assert len(out) == 1 and out[0]["kind"] == "PERCENT"

    def test_exact_limit_passes(self):
        assert findings_for(audit_percents, "upper limit of 35\\%", self.Q) == []

    def test_definitional_percentages_are_exempt(self):
        for text in ("exact 95\\% CI", "falls below 5\\%", "more than 20\\% errored runs"):
            assert findings_for(audit_percents, text, self.Q) == [], text

    def test_url_percent_encoding_is_not_a_percentage(self):
        """python-3.11%2B in a badge URL is encoding, not a measurement."""
        text = 'src="https://img.shields.io/badge/python-3.11%2B-blue"'
        assert findings_for(audit_percents, text, self.Q) == []
