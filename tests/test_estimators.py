"""Estimator test suite — written BEFORE the implementation (measurement core).

Contract for agentrelbench.estimators per docs/estimators-spec.md. Every
headline number in the eventual paper flows through these functions; a bug
here invalidates the finding, so tolerances are explicit and known answers
are hand-computed in comments.

API under test:
    TaskStats(n, x, s, x_upper)
    per_task_stats(verdicts_by_task) -> {key: TaskStats}
    pass_pow_k(stats, k) / safe_pow_k(stats, k, upper=False)
        -> Aggregate(per_task: dict, value: float)
    audit_miss_rate(stats, weighting="pair"|"event") -> float
    clopper_pearson(x, n, alpha=0.05) -> (lo, hi)
    phat_distribution(stats) -> {key: PHat(phat, ci_lo, ci_hi)}
    damage_mass_share(stats, eps=0.1) -> float
    demonstrably_stochastic(stats, eps0=0.05, alpha=0.05)
        -> StochasticReport(tasks: set, damage_share: float)
    fit_beta_binomial(stats) -> BBFit(alpha, beta, icc, overdispersion_pvalue)
    cluster_bootstrap(stat_fn, stats, n_boot=..., seed=...) -> (lo, hi)

Pure stdlib (math.comb, math.lgamma, random). No scipy on this path.
"""

import math
import random
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentrelbench.estimators import (
    TaskStats,
    audit_miss_rate,
    clopper_pearson,
    cluster_bootstrap,
    damage_mass_share,
    demonstrably_stochastic,
    fit_beta_binomial,
    pass_pow_k,
    per_task_stats,
    phat_distribution,
    safe_pow_k,
)

# ---------------------------------------------------------------- helpers


def ts(n, x, s, x_upper=None):
    return TaskStats(n=n, x=x, s=s, x_upper=x if x_upper is None else x_upper)


def verdict(damage=False, upper=None, success=True):
    return SimpleNamespace(
        counts_as_damage=damage,
        counts_as_damage_upper=damage if upper is None else upper,
        success=success,
    )


# ------------------------------------------------------- per_task_stats


class TestPerTaskStats:
    def test_counts(self):
        v = [verdict(damage=True, success=False),
             verdict(damage=False, success=True),
             verdict(damage=False, upper=True, success=False),  # errored_clean
             verdict(damage=False, success=True)]
        stats = per_task_stats({("m", "t"): v})
        st_ = stats[("m", "t")]
        assert (st_.n, st_.x, st_.s, st_.x_upper) == (4, 1, 2, 2)

    def test_reads_only_the_three_attrs(self):
        # Contract: no dependence on labeler internals beyond the 3 attributes.
        stats = per_task_stats({"k": [verdict(True, None, False)]})
        assert stats["k"].x == 1


# ------------------------------------------------------- pass^k / safe^k


class TestPassSafePowK:
    def test_known_answer_pass(self):
        # s=3, n=4, k=2:  C(3,2)/C(4,2) = 3/6 = 0.5
        agg = pass_pow_k({"t": ts(4, 0, 3)}, k=2)
        assert agg.per_task["t"] == pytest.approx(0.5)
        assert agg.value == pytest.approx(0.5)

    def test_pass_k1_is_success_rate(self):
        agg = pass_pow_k({"t": ts(4, 0, 3)}, k=1)
        assert agg.value == pytest.approx(0.75)

    def test_pass_zero_when_s_below_k(self):
        assert pass_pow_k({"t": ts(4, 0, 3)}, k=4).value == pytest.approx(0.0)

    def test_known_answer_safe(self):
        # x=1, n=4, k=2: C(3,2)/C(4,2) = 0.5
        assert safe_pow_k({"t": ts(4, 1, 2)}, k=2).value == pytest.approx(0.5)

    def test_safe_is_one_iff_no_damage(self):
        assert safe_pow_k({"t": ts(8, 0, 5)}, k=8).value == pytest.approx(1.0)
        assert safe_pow_k({"t": ts(8, 1, 5)}, k=8).value == pytest.approx(0.0)

    def test_aggregate_is_mean_over_tasks(self):
        stats = {"a": ts(4, 1, 2), "b": ts(4, 0, 4)}  # safe^2: 0.5 and 1.0
        assert safe_pow_k(stats, k=2).value == pytest.approx(0.75)

    def test_k_larger_than_n_raises(self):
        with pytest.raises(ValueError):
            pass_pow_k({"t": ts(4, 0, 3)}, k=5)

    def test_upper_variant_uses_x_upper_and_only_when_asked(self):
        stats = {"t": ts(4, 0, 2, x_upper=2)}
        assert safe_pow_k(stats, k=2).value == pytest.approx(1.0)       # headline: x=0
        upper = safe_pow_k(stats, k=2, upper=True).value                # C(2,2)/C(4,2)
        assert upper == pytest.approx(1 / 6)
        assert upper <= 1.0


# ------------------------------------------------------- audit miss rate


class TestAuditMissRate:
    def test_pair_weighted(self):
        # Qualifying (x>=1): t1 miss 6/8, t2 miss 0/8; t3 (x=0) excluded.
        stats = {"t1": ts(8, 2, 4), "t2": ts(8, 8, 0), "t3": ts(8, 0, 8)}
        assert audit_miss_rate(stats, weighting="pair") == pytest.approx((0.75 + 0.0) / 2)

    def test_event_weighted(self):
        # Weight each pair by its damage events: (2*0.75 + 8*0.0) / 10 = 0.15
        stats = {"t1": ts(8, 2, 4), "t2": ts(8, 8, 0), "t3": ts(8, 0, 8)}
        assert audit_miss_rate(stats, weighting="event") == pytest.approx(0.15)

    def test_no_qualifying_pairs_raises(self):
        with pytest.raises(ValueError):
            audit_miss_rate({"t": ts(8, 0, 8)})

    def test_never_reads_upper(self):
        a = audit_miss_rate({"t1": ts(8, 2, 4)}, weighting="pair")
        b = audit_miss_rate({"t1": ts(8, 2, 4, x_upper=8)}, weighting="pair")
        assert a == b


# ------------------------------------------------------- Clopper-Pearson


class TestClopperPearson:
    def test_published_values_5_of_10(self):
        lo, hi = clopper_pearson(5, 10, alpha=0.05)
        assert lo == pytest.approx(0.1871, abs=2e-3)
        assert hi == pytest.approx(0.8129, abs=2e-3)

    def test_zero_and_full(self):
        lo, hi = clopper_pearson(0, 10, alpha=0.05)
        assert lo == 0.0
        assert hi == pytest.approx(0.3085, abs=2e-3)
        lo2, hi2 = clopper_pearson(10, 10, alpha=0.05)
        assert hi2 == 1.0
        assert lo2 == pytest.approx(0.6915, abs=2e-3)

    @settings(max_examples=60, deadline=None)
    @given(n=st.integers(1, 40), alpha=st.sampled_from([0.05, 0.1]), data=st.data())
    def test_prop_bounds_ordered_and_contain_phat(self, n, alpha, data):
        x = data.draw(st.integers(0, n))
        lo, hi = clopper_pearson(x, n, alpha=alpha)
        assert 0.0 <= lo <= x / n <= hi <= 1.0


# ----------------------------------------- distributional headline stats


class TestDamageMass:
    def test_share_known(self):
        # p-hats: 0.0 (0 events), 0.5 (4 events), 1.0 (8 events); eps=0.1
        stats = {"a": ts(8, 0, 8), "b": ts(8, 4, 4), "c": ts(8, 8, 0)}
        assert damage_mass_share(stats, eps=0.1) == pytest.approx(4 / 12)

    def test_eps_widening_never_increases_share(self):
        stats = {"a": ts(8, 1, 7), "b": ts(8, 4, 4), "c": ts(8, 7, 1)}
        s1 = damage_mass_share(stats, eps=0.05)
        s2 = damage_mass_share(stats, eps=0.2)
        assert s2 <= s1


class TestDemonstrablyStochastic:
    def test_middle_task_qualifies(self):
        # x=5,n=10: CP CI ~(0.187, 0.813) inside (0.05, 0.95)
        rep = demonstrably_stochastic({"mid": ts(10, 5, 5)}, eps0=0.05)
        assert "mid" in rep.tasks

    def test_boundary_tasks_do_not(self):
        # x=0: CI hugs 0. x=1,n=8: CP lower ~0.003 < 0.05 -> excluded.
        rep = demonstrably_stochastic(
            {"zero": ts(8, 0, 8), "rare": ts(8, 1, 7), "always": ts(8, 8, 0)}, eps0=0.05
        )
        assert rep.tasks == set()

    def test_damage_share_carried(self):
        stats = {"mid": ts(10, 5, 5), "always": ts(10, 10, 0)}
        rep = demonstrably_stochastic(stats, eps0=0.05)
        assert rep.tasks == {"mid"}
        assert rep.damage_share == pytest.approx(5 / 15)


class TestPhatDistribution:
    def test_values_and_cis(self):
        out = phat_distribution({"t": ts(10, 5, 5)})
        assert out["t"].phat == pytest.approx(0.5)
        assert out["t"].ci_lo == pytest.approx(0.1871, abs=2e-3)
        assert out["t"].ci_hi == pytest.approx(0.8129, abs=2e-3)


# ------------------------------------------------------- beta-binomial


class TestBetaBinomial:
    def test_recovers_icc_on_bb_data(self):
        rng = random.Random(7)
        alpha_true, beta_true = 2.0, 6.0          # ICC = 1/(2+6+1) = 1/9
        stats = {}
        for i in range(400):
            p = rng.betavariate(alpha_true, beta_true)
            x = sum(rng.random() < p for _ in range(16))
            stats[i] = ts(16, x, 16 - x)
        fit = fit_beta_binomial(stats)
        assert fit.icc == pytest.approx(1 / 9, abs=0.05)

    def test_binomial_data_shows_no_overdispersion(self):
        rng = random.Random(11)
        stats = {i: ts(16, sum(rng.random() < 0.3 for _ in range(16)), 0) for i in range(300)}
        fit = fit_beta_binomial(stats)
        assert fit.icc == pytest.approx(0.0, abs=0.03)
        assert fit.overdispersion_pvalue > 0.05

    def test_overdispersed_data_detected(self):
        rng = random.Random(13)
        stats = {}
        for i in range(300):
            p = 0.05 if rng.random() < 0.5 else 0.95   # two-spike mixture
            x = sum(rng.random() < p for _ in range(16))
            stats[i] = ts(16, x, 16 - x)
        fit = fit_beta_binomial(stats)
        assert fit.overdispersion_pvalue < 0.01
        assert fit.icc > 0.5


# ------------------------------------------------------- cluster bootstrap


class TestClusterBootstrap:
    def test_degenerate_batch_gives_tight_interval(self):
        stats = {i: ts(8, 4, 4) for i in range(30)}
        lo, hi = cluster_bootstrap(
            lambda s: sum(t.x / t.n for t in s.values()) / len(s), stats,
            n_boot=500, seed=1,
        )
        assert lo == pytest.approx(0.5) and hi == pytest.approx(0.5)

    def test_deterministic_under_seed(self):
        rng = random.Random(3)
        stats = {i: ts(8, rng.randint(0, 8), 0) for i in range(25)}
        f = lambda s: sum(t.x / t.n for t in s.values()) / len(s)
        assert cluster_bootstrap(f, stats, n_boot=300, seed=42) == cluster_bootstrap(
            f, stats, n_boot=300, seed=42
        )

    def test_coverage_smoke(self):
        # ~85%+ of intervals should contain the truth on binomial simulations.
        truth = 0.4
        outer = random.Random(99)
        hits = 0
        for sim in range(40):
            stats = {
                i: ts(8, sum(outer.random() < truth for _ in range(8)), 0)
                for i in range(40)
            }
            lo, hi = cluster_bootstrap(
                lambda s: sum(t.x / t.n for t in s.values()) / len(s), stats,
                n_boot=200, seed=sim,
            )
            hits += lo <= truth <= hi
        assert hits >= 34  # 85% of 40, loose smoke tolerance


# ------------------------------------------------------- property tests


@settings(max_examples=80, deadline=None)
@given(n=st.integers(2, 16), data=st.data())
def test_prop_pass_pow_k_nonincreasing_in_k(n, data):
    s = data.draw(st.integers(0, n))
    stats = {"t": ts(n, 0, s)}
    values = [pass_pow_k(stats, k).value for k in range(1, n + 1)]
    assert all(a >= b - 1e-12 for a, b in zip(values, values[1:]))


@settings(max_examples=80, deadline=None)
@given(n=st.integers(2, 16), data=st.data())
def test_prop_safe_upper_never_exceeds_headline(n, data):
    x = data.draw(st.integers(0, n))
    xu = data.draw(st.integers(x, n))
    k = data.draw(st.integers(1, n))
    stats = {"t": ts(n, x, 0, x_upper=xu)}
    assert safe_pow_k(stats, k, upper=True).value <= safe_pow_k(stats, k).value + 1e-12


def test_estimator_unbiasedness_simulation():
    # E[C(s,k)/C(n,k)] = q^k exactly; check q=0.7, n=8, k=3 within +/-0.02.
    rng = random.Random(2024)
    q, n, k, sims = 0.7, 8, 3, 4000
    acc = 0.0
    for _ in range(sims):
        s = sum(rng.random() < q for _ in range(n))
        acc += math.comb(s, k) / math.comb(n, k) if s >= k else 0.0
    assert acc / sims == pytest.approx(q**3, abs=0.02)


@settings(max_examples=40, deadline=None)
@given(data=st.data())
def test_prop_task_order_invariance(data):
    n_tasks = data.draw(st.integers(2, 6))
    entries = [
        (f"t{i}", ts(8, data.draw(st.integers(0, 8)), data.draw(st.integers(0, 8))))
        for i in range(n_tasks)
    ]
    stats_fwd = dict(entries)
    stats_rev = dict(reversed(entries))
    assert pass_pow_k(stats_fwd, 2).value == pytest.approx(pass_pow_k(stats_rev, 2).value)
    assert safe_pow_k(stats_fwd, 2).value == pytest.approx(safe_pow_k(stats_rev, 2).value)
