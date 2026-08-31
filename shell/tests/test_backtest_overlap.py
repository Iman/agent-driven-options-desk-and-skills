"""The backtest's significance tests must know that its windows overlap.

Entries every five trading days with a thirty day hold share twenty-five of
their thirty days. An audit measured the consequence on this project's own
artifacts: autocorrelation positive through lag five, collapsing at lag six,
an effective sample of 64 to 88 rather than 233, standard errors understated
by a factor of 1.6 to 1.9, and three structures crossing the 0.05 line once
the dependence was accounted for. One went from 0.0005 to 0.068.

The command has to derive the block from its own settings and pass it. This
file exists because the engine can be perfectly correct while the caller
asks it the wrong question.
"""

import pytest

from optiondesk import engine_bridge
from optiondesk.artifacts import read_json

from marks import needs_engine

pytestmark = needs_engine


def _run_with(monkeypatch, returns, tmp_path, holding=30, spacing=5):
    """Drive the command with a fixed backtest result, no network."""
    engine = engine_bridge.backtest()
    trades = [{"entry_date": "2026-01-01", "exit_date": "2026-02-01",
               "entry_spot": 100.0, "exit_spot": 101.0,
               "underlying_return": 0.01, "entry_volatility": 0.2,
               "net_cash": 1.0, "trade_type": "credit",
               "capital_at_risk": 10.0, "profit": value * 10.0,
               "return_on_risk": value} for value in returns]
    result = {"trades": trades, "returns": list(returns), "skipped": [],
              "first_date": "2021-08-30", "last_date": "2026-08-28",
              "premium_source": "model", "honesty": "modelled premiums",
              "settings": {"holding_days": holding, "entry_every": spacing,
                           "lookback": 60, "size": 1.0}}
    monkeypatch.setattr(engine, "run_backtest", lambda *a, **k: result)

    history = {"closes": [100.0 + i * 0.1 for i in range(400)],
               "dates": ["2026-01-{:02d}".format(1 + i % 28)
                         for i in range(400)],
               "symbol": "SYN", "period": "5y",
               "first": "2021-08-30", "last": "2026-08-28"}

    class Provider:
        name = "stub"

        def underlying_history(self, symbol, period="5y"):
            return history

    from optiondesk.cli import backtest as backtest_cmd
    monkeypatch.setattr(backtest_cmd, "resolve",
                        lambda capability, preferred=None: (
                            Provider(), {"degraded": False, "skipped": []}))

    class Args:
        symbol = "SYN"
        strategy = "iron_condor"
        holding_days = holding
        entry_every = spacing
        lookback = 60
        period = "5y"
        rate = 0.04
        dividend_yield = 0.0
        size = 1.0
        provider = None
        out_dir = str(tmp_path)

    return backtest_cmd.run(Args())


def _correlated(n=240, rho=0.85, shift=0.35, seed=5):
    import random

    rng = random.Random(seed)
    series, value = [], 0.0
    for _ in range(n):
        value = rho * value + rng.gauss(0.0, 1.0)
        series.append(value + shift)
    return series


def test_the_command_passes_the_overlap_block_to_the_test(monkeypatch,
                                                          tmp_path):
    """Thirty over five is six, and six is where the measured
    autocorrelation collapses on this schedule. The engine can be perfectly
    correct while the caller asks it the wrong question, so this asserts
    what the caller actually asked.
    """
    summary = _run_with(monkeypatch, _correlated(), tmp_path)
    assert summary["overlap_block"] == 6, (
        "the command reported block {}".format(summary["overlap_block"]))
    note = " ".join(summary.get("notes") or [])
    assert "Entries overlap" in note, note


def test_a_schedule_without_overlap_blocks_nothing(monkeypatch, tmp_path):
    """The block is derived, not assumed. Entries spaced at or beyond the
    holding period do not overlap, and blocking them would throw away
    power for nothing.
    """
    summary = _run_with(monkeypatch, _correlated(), tmp_path,
                        holding=30, spacing=30)
    assert summary["overlap_block"] == 1
    note = " ".join(summary.get("notes") or [])
    assert "Entries overlap" not in note


def test_blocking_moves_the_p_value_on_this_data(monkeypatch, tmp_path):
    """The whole point, end to end: the same returns through the same
    command give a larger p-value once the overlap is respected.
    """
    overlapping = _run_with(monkeypatch, _correlated(), tmp_path,
                            holding=30, spacing=5)
    independent = _run_with(monkeypatch, _correlated(), tmp_path,
                            holding=30, spacing=30)
    assert overlapping["p_value"] > independent["p_value"], (
        "block {} gave {} against block {} giving {}".format(
            overlapping["overlap_block"], overlapping["p_value"],
            independent["overlap_block"], independent["p_value"]))
