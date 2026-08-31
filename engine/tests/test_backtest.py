"""Backtest runner and its statistics.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.

The runner's honesty properties are tested as behaviour, not as prose: a
result that omits the modelled-premium statement, or that prices an entry
using volatility from the future, would pass a naive test and fail these.
"""

import math
import random

import pytest

from optiondesk_engine import strategies as strategies_module
from optiondesk_engine.backtest.runner import (
    realised_volatility,
    run_backtest,
    synthetic_chain,
)
from optiondesk_engine.backtest.stats import (
    bootstrap_mean_interval,
    performance_stats,
    permutation_p_value,
)
from optiondesk_engine.pricing.black_scholes import bs_price


def _series(n=600, sigma=0.18, drift=0.0, seed=3, spot=100.0):
    rng = random.Random(seed)
    daily = sigma / math.sqrt(252)
    prices = [spot]
    dates = []
    for i in range(n):
        prices.append(prices[-1] * math.exp(drift / 252
                                            + rng.gauss(0.0, daily)))
        dates.append("2024-01-{:02d}".format((i % 28) + 1))
    dates.append("2026-01-01")
    return prices, dates


def test_realised_volatility_recovers_a_known_input():
    rng = random.Random(11)
    daily = 0.20 / math.sqrt(252)
    returns = [rng.gauss(0.0, daily) for _ in range(2000)]
    assert realised_volatility(returns) == pytest.approx(0.20, rel=0.08)
    assert realised_volatility([0.001] * 5) is None


def test_synthetic_chain_is_priced_and_two_sided():
    chain = synthetic_chain(bs_price, 100.0, 30, 0.20)
    calls = [c for c in chain["contracts"] if c["type"] == "call"]
    puts = [c for c in chain["contracts"] if c["type"] == "put"]
    assert calls and puts
    assert all(c["mid"] > 0 and c["iv"] == 0.20 for c in chain["contracts"])
    # Every contract must be priced by the model, and say so, so a reader
    # cannot mistake this for quoted data.
    assert all(c["iv_source"] == "model" for c in chain["contracts"])


def test_a_backtest_produces_trades_and_carries_the_honesty_statement():
    prices, dates = _series()
    result = run_backtest(strategies_module, bs_price, prices, dates,
                          "iron_condor", holding_days=30, entry_every=10)
    assert result["trades"]
    assert result["premium_source"] == "model"
    for phrase in ("not quotes and not fills", "no spread", "payoff "
                   "geometry"):
        assert phrase in result["honesty"]
    for trade in result["trades"]:
        assert trade["entry_date"] and trade["exit_date"]
        assert trade["entry_spot"] > 0 and trade["exit_spot"] > 0
        assert trade["profit"] is not None


def test_entry_volatility_uses_only_the_past():
    """Lookahead is the classic way a backtest lies.

    A volatility regime that changes sharply partway through must not
    affect the entry volatility of trades opened before it. If the runner
    ever estimated volatility over the holding period instead of the
    trailing window, the early entries would already know about the later
    regime and this would fail.
    """
    calm, dates_calm = _series(n=300, sigma=0.10, seed=4)
    wild, _ = _series(n=300, sigma=0.60, seed=5, spot=calm[-1])
    prices = calm + wild[1:]
    dates = ["d{}".format(i) for i in range(len(prices))]

    result = run_backtest(strategies_module, bs_price, prices, dates,
                          "long_call", holding_days=20, entry_every=10,
                          lookback=60)
    early = [t["entry_volatility"] for t in result["trades"][:5]]
    late = [t["entry_volatility"] for t in result["trades"][-5:]]
    assert max(early) < min(late), (
        "early entries priced with knowledge of the later regime")


def test_too_little_history_is_an_error_not_an_empty_result():
    prices, dates = _series(n=40)
    with pytest.raises(ValueError):
        run_backtest(strategies_module, bs_price, prices, dates,
                     "iron_condor", holding_days=30)


def test_mismatched_prices_and_dates_are_refused():
    prices, dates = _series(n=200)
    with pytest.raises(ValueError):
        run_backtest(strategies_module, bs_price, prices, dates[:-5],
                     "long_call")


def test_an_unbuildable_strategy_is_named():
    prices, dates = _series(n=300)
    with pytest.raises(ValueError):
        run_backtest(strategies_module, bs_price, prices, dates,
                     "calendar_spread", holding_days=20)


def test_skipped_entries_are_recorded_not_dropped():
    prices, dates = _series(n=400)
    result = run_backtest(strategies_module, bs_price, prices, dates,
                          "iron_condor", holding_days=30, entry_every=5)
    assert isinstance(result["skipped"], list)
    for entry in result["skipped"]:
        assert entry["date"] and entry["reason"]


def test_performance_stats_on_a_known_series():
    returns = [0.1, -0.05, 0.2, -0.1, 0.05]
    stats = performance_stats(returns, holding_days=30)
    assert stats["trades"] == 5
    assert stats["win_rate"] == pytest.approx(0.6)
    assert stats["mean_return"] == pytest.approx(0.04)
    assert stats["best"] == 0.2 and stats["worst"] == -0.1
    assert stats["max_drawdown_in_risk_units"] > 0
    # Fixed risk per trade: the sum of the returns, not their product.
    assert stats["total_return_on_risk"] == pytest.approx(0.2)
    assert "one unit of capital at risk per trade" in stats["accounting"]
    assert stats["profit_factor"] == pytest.approx(0.35 / 0.15)
    assert "sharpe_annualised" in stats


def test_annualisation_is_withheld_without_a_holding_period():
    stats = performance_stats([0.1, -0.05, 0.2])
    assert "sharpe_annualised" not in stats


def test_permutation_test_finds_nothing_in_noise():
    rng = random.Random(21)
    noise = [rng.gauss(0.0, 0.1) for _ in range(200)]
    result = permutation_p_value(noise)
    assert result["p_value"] > 0.05
    assert "already spent its degrees of freedom" in result["caveat"]


def test_permutation_test_finds_a_real_effect():
    rng = random.Random(22)
    biased = [rng.gauss(0.05, 0.05) for _ in range(200)]
    assert permutation_p_value(biased)["p_value"] < 0.01


def test_bootstrap_interval_brackets_the_mean():
    rng = random.Random(23)
    returns = [rng.gauss(0.02, 0.1) for _ in range(300)]
    interval = bootstrap_mean_interval(returns)
    assert interval["lower"] < interval["mean"] < interval["upper"]
    assert interval["excludes_zero"] is True


def test_the_interval_has_roughly_its_stated_coverage():
    """A 90 percent interval must exclude zero about a tenth of the time.

    Asserting that one particular noise sample does not exclude zero tests
    luck: under the null it will exclude about one time in ten, so such a
    test fails intermittently for the correct implementation. The property
    worth testing is the frequency, so twenty samples are drawn and most
    must behave. An interval that was far too narrow, which is the actual
    bug this guards against, would exclude zero in most of them.
    """
    excluded = 0
    for seed in range(20):
        rng = random.Random(500 + seed)
        noise = [rng.gauss(0.0, 0.1) for _ in range(300)]
        if bootstrap_mean_interval(noise)["excludes_zero"]:
            excluded += 1
    assert excluded <= 6, (
        "{} of 20 null samples excluded zero; the interval is too "
        "narrow".format(excluded))


def test_statistics_refuse_a_sample_too_small_to_speak_about():
    assert permutation_p_value([0.1, 0.2]) is None
    assert bootstrap_mean_interval([0.1, 0.2]) is None
    assert performance_stats([]) is None


def test_the_permutation_test_flips_whole_blocks():
    """Overlapping windows are not independent trades, and treating them as
    such understates the standard error.

    A thirty day hold entered every five trading days shares twenty-five of
    its thirty days with its neighbour. An audit measured the effect on
    this project's own artifacts: autocorrelation positive through lag five
    and collapsing at lag six, an effective sample of 64 to 88 rather than
    233, and three structures crossing 0.05 once the dependence was
    accounted for, one of them from 0.0005 to 0.068.

    A serially correlated series is the discriminating input. Independent
    sign flips break the correlation and produce a small p-value; block
    flips preserve it and produce an honest one.
    """
    import random

    rng = random.Random(5)
    series, value = [], 0.0
    for _ in range(240):
        value = 0.85 * value + rng.gauss(0.0, 1.0)
        series.append(value + 0.35)

    independent = permutation_p_value(series, trials=2000, block=1)
    blocked = permutation_p_value(series, trials=2000, block=6)

    assert independent["block"] == 1
    assert blocked["block"] == 6
    assert blocked["p_value"] > independent["p_value"], (
        "blocking did not widen the null: {} against {}".format(
            blocked["p_value"], independent["p_value"]))


def test_the_interval_widens_when_trades_overlap():
    """The same argument for the confidence interval. Resampling single
    trades from a correlated series produces an interval too narrow, and on
    the live artifacts it was narrow enough to exclude zero for two
    structures that a moving-block interval does not.
    """
    import random

    rng = random.Random(7)
    series, value = [], 0.0
    for _ in range(240):
        value = 0.85 * value + rng.gauss(0.0, 1.0)
        series.append(value + 0.2)

    single = bootstrap_mean_interval(series, trials=2000, block=1)
    blocked = bootstrap_mean_interval(series, trials=2000, block=6)

    assert blocked["block"] == 6
    width_single = single["upper"] - single["lower"]
    width_blocked = blocked["upper"] - blocked["lower"]
    assert width_blocked > width_single, (
        "the block interval is not wider: {} against {}".format(
            width_blocked, width_single))
