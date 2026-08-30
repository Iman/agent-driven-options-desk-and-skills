"""GARCH-t posterior and forward path simulation.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.

The decisive test is parameter recovery: simulate returns from known
parameters, sample the posterior, and require the intervals to contain the
truth. A sampler that cannot recover an answer it was given has no business
being pointed at a market.
"""

import math
import random

import pytest

from optiondesk_engine.simulation.garch import (
    fit_garch_t,
    garch_log_likelihood,
)
from optiondesk_engine.simulation.paths import (
    position_distribution,
    simulate_paths,
    terminal_risk,
)

TRUTH = {"mu": 0.0004, "omega": 2.0e-6, "alpha": 0.09, "beta": 0.88,
         "nu": 6.0}


def _synthetic(n=900, seed=5, truth=None):
    truth = truth or TRUTH
    rng = random.Random(seed)
    variance = truth["omega"] / (1.0 - truth["alpha"] - truth["beta"])
    out = []
    for _ in range(n):
        chi2 = rng.gammavariate(truth["nu"] / 2.0, 2.0)
        z = rng.gauss(0.0, 1.0) / math.sqrt(chi2 / truth["nu"])
        z *= math.sqrt((truth["nu"] - 2.0) / truth["nu"])
        residual = math.sqrt(variance) * z
        out.append(truth["mu"] + residual)
        variance = (truth["omega"] + truth["alpha"] * residual * residual
                    + truth["beta"] * variance)
    return out


@pytest.fixture(scope="module")
def posterior():
    return fit_garch_t(_synthetic(), draws=3000, burn=1000, chains=2)


def test_the_posterior_recovers_parameters_it_was_given():
    """Coverage across datasets, not perfection on one.

    A 90 percent interval is supposed to miss about one time in ten, so
    demanding that a single dataset cover all five parameters tests luck as
    much as correctness, and fails intermittently on whichever parameter is
    least identified. Degrees of freedom is that parameter here: the data
    constrains the tail weakly by nature.

    Three datasets, fifteen interval checks, and at least twelve must
    contain the truth. Under correct 90 percent coverage the expected count
    is thirteen and a half, and a genuinely broken sampler misses far more
    than three.
    """
    covered = 0
    misses = []
    for seed in (5, 17, 29):
        posterior = fit_garch_t(_synthetic(seed=seed), draws=2000, burn=800,
                                chains=2)
        summary = posterior.summary()
        for name, true_value in TRUTH.items():
            stats = summary[name]
            if stats["p5"] <= true_value <= stats["p95"]:
                covered += 1
            else:
                misses.append("seed {} {}: true {} outside [{:.4g}, {:.4g}]"
                              .format(seed, name, true_value, stats["p5"],
                                      stats["p95"]))
    assert covered >= 12, "only {} of 15 intervals covered: {}".format(
        covered, "; ".join(misses))


def test_the_posterior_is_centred_on_the_truth(posterior):
    """Separate from coverage: the medians must be in the right place."""
    summary = posterior.summary()
    assert abs(summary["alpha"]["p50"] - TRUTH["alpha"]) < 0.05
    assert abs(summary["beta"]["p50"] - TRUTH["beta"]) < 0.08
    # Volatility level, which is what actually drives a forecast, must be
    # close in relative terms.
    implied = summary["omega"]["p50"] / (1.0 - summary["alpha"]["p50"]
                                         - summary["beta"]["p50"])
    true_variance = TRUTH["omega"] / (1.0 - TRUTH["alpha"] - TRUTH["beta"])
    assert 0.5 < implied / true_variance < 2.0


def test_the_chains_agree_and_carry_enough_information(posterior):
    diagnostics = posterior.diagnostics
    assert posterior.converged is True
    for name in ("mu", "omega", "alpha", "beta", "nu"):
        assert diagnostics["rhat"][name] < diagnostics["rhat_limit"]
        assert diagnostics["ess"][name] >= diagnostics["min_ess"]
    assert 0.15 < diagnostics["acceptance_rate"] < 0.60


def test_likelihood_refuses_parameters_outside_the_model():
    returns = _synthetic(n=200)
    assert garch_log_likelihood(returns, 0.0, -1e-6, 0.1, 0.8, 6) == \
        float("-inf")
    assert garch_log_likelihood(returns, 0.0, 1e-6, 0.5, 0.6, 6) == \
        float("-inf")   # not stationary
    assert garch_log_likelihood(returns, 0.0, 1e-6, 0.1, 0.8, 1.5) == \
        float("-inf")   # no finite variance
    assert garch_log_likelihood(returns[:5], 0.0, 1e-6, 0.1, 0.8, 6) == \
        float("-inf")   # too little data


def test_likelihood_prefers_the_truth_to_a_wrong_answer():
    returns = _synthetic()
    good = garch_log_likelihood(returns, **TRUTH)
    for wrong in ({"alpha": 0.35, "beta": 0.5}, {"nu": 40.0},
                  {"omega": 2.0e-5}):
        params = dict(TRUTH)
        params.update(wrong)
        assert good > garch_log_likelihood(returns, **params)


def test_too_few_returns_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        fit_garch_t([0.001] * 20)


def test_the_fan_widens_with_horizon(posterior):
    simulation = simulate_paths(posterior, 100.0, 10, paths=4000, seed=3)
    fan = simulation["fan"]
    assert len(fan) == 10
    first = fan[0]["p95"] - fan[0]["p5"]
    last = fan[-1]["p95"] - fan[-1]["p5"]
    assert last > first * 1.5
    # The median stays near spot: this model has almost no drift.
    assert abs(fan[-1]["p50"] / 100.0 - 1.0) < 0.05


def test_paths_are_antithetic_and_counted(posterior):
    simulation = simulate_paths(posterior, 100.0, 5, paths=1000, seed=3)
    assert simulation["antithetic"] is True
    assert simulation["paths"] == 1000
    assert len(simulation["terminal"]) == 1000
    assert simulation["terminal"] == sorted(simulation["terminal"])


def test_risk_numbers_are_ordered_as_their_definitions_require(posterior):
    simulation = simulate_paths(posterior, 100.0, 5, paths=8000, seed=3)
    risk = terminal_risk(simulation)
    # Expected shortfall is the mean beyond the value at risk, so it is
    # always the larger loss. A pipeline that reports otherwise has them
    # swapped, which is a common and expensive mistake.
    assert risk["es_95"] > risk["var_95"] > 0
    assert risk["es_99"] > risk["var_99"] > 0
    assert risk["var_99"] > risk["var_95"]
    assert 0.3 < risk["probability_up"] < 0.7


def test_a_fat_tailed_model_produces_a_fatter_tail_than_a_normal_one():
    # Low degrees of freedom must show up as a wider extreme quantile than
    # a nearly normal model with the same volatility.
    fat = fit_garch_t(_synthetic(truth=dict(TRUTH, nu=3.5), seed=9),
                      draws=1200, burn=600, chains=2)
    thin = fit_garch_t(_synthetic(truth=dict(TRUTH, nu=40.0), seed=9),
                       draws=1200, burn=600, chains=2)
    fat_risk = terminal_risk(simulate_paths(fat, 100.0, 5, paths=8000,
                                            seed=4))
    thin_risk = terminal_risk(simulate_paths(thin, 100.0, 5, paths=8000,
                                             seed=4))
    assert fat_risk["es_99"] > thin_risk["es_99"]


def test_position_distribution_matches_a_hand_computed_payoff(posterior):
    simulation = simulate_paths(posterior, 100.0, 5, paths=4000, seed=3)
    # A long call struck at 100 costing 2: profit is intrinsic minus premium.
    distribution = position_distribution(
        simulation, lambda price: max(price - 100.0, 0.0) - 2.0)
    assert distribution["worst"] == pytest.approx(-2.0)
    assert distribution["best"] > 0
    assert 0.0 <= distribution["probability_of_profit"] <= 1.0
    assert distribution["p5"] <= distribution["median"] <= distribution["p95"]
    assert sum(bucket["count"] for bucket in distribution["histogram"]) == \
        simulation["paths"]
    assert distribution["expected_shortfall_5"] <= distribution["p5"] + 1e-9


def test_simulation_rejects_impossible_requests(posterior):
    with pytest.raises(ValueError):
        simulate_paths(posterior, 0.0, 5)
    with pytest.raises(ValueError):
        simulate_paths(posterior, 100.0, 0)
