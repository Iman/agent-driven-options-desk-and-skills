"""A backtest must say which problem it hit, not the wrong one.

WHAT WOULD BREAK. The trade count in the summary came from the list of
returns on capital at risk, and a trade only reaches that list when the
capital is definable. A ratio spread has an unbounded maximum loss, so
every one of its trades has no denominator: the run entered 52 trades and
reported "only 0 trades: too few for any statistic here to carry weight".

Both halves of that sentence are wrong. There were 52 trades, and the
problem is not that there were too few, it is that return on risk has no
denominator for this structure. A reader would go looking for missing price
history that is not missing.
"""

import pytest

from optiondesk.cli import backtest as backtest_cmd


class _Result(dict):
    pass


def _run_with(monkeypatch, trades, returns, tmp_path):
    """Drive the command with a fixed backtest result."""
    engine = backtest_cmd.engine_bridge.backtest()

    result = {
        "trades": trades, "returns": returns, "skipped": [],
        "first_date": "2021-08-30", "last_date": "2026-08-28",
        "premium_source": "model",
        "honesty": ("Real underlying closes, modelled premiums, no spread "
                    "and no slippage."),
        "settings": {"holding_days": 30, "entry_every": 5, "lookback": 60,
                     "size": 1.0},
    }

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

    monkeypatch.setattr(
        backtest_cmd, "resolve",
        lambda capability, preferred=None: (
            Provider(), {"degraded": False, "skipped": []}))

    class Args:
        symbol = "SYN"
        strategy = "ratio_spread"
        holding_days = 30
        entry_every = 5
        lookback = 60
        period = "5y"
        rate = 0.04
        dividend_yield = 0.0
        size = 1.0
        provider = None
        out_dir = str(tmp_path)

    return backtest_cmd.run(Args())


def _trade(profit, capital):
    return {"entry_date": "2026-01-01", "exit_date": "2026-02-01",
            "entry_spot": 100.0, "exit_spot": 101.0,
            "underlying_return": 0.01, "entry_volatility": 0.2,
            "net_cash": 1.0, "trade_type": "credit",
            "capital_at_risk": capital, "profit": profit,
            "return_on_risk": (profit / capital) if capital else None}


def test_trades_without_a_denominator_are_not_reported_as_no_trades(
        monkeypatch, tmp_path):
    trades = [_trade(1.0, None) for _ in range(52)]
    summary = _run_with(monkeypatch, trades, [], tmp_path)

    assert summary["trades_entered"] == 52, (
        "the summary must say how many trades were actually entered")
    note = " ".join(summary.get("notes") or [])
    assert "52 trades were entered" in note, note
    assert "unbounded" in note, note
    assert "too few" not in note, (
        "the run did not have too few trades, it had no denominator: " + note)


def test_a_genuinely_short_run_still_says_too_few(monkeypatch, tmp_path):
    """The original note is right for the case it was written for."""
    trades = [_trade(1.0, 10.0) for _ in range(4)]
    summary = _run_with(monkeypatch, trades, [0.1] * 4, tmp_path)
    note = " ".join(summary.get("notes") or [])
    assert "only 4 trades" in note, note
    assert "unbounded" not in note, note


def test_a_partial_loss_of_denominators_is_counted(monkeypatch, tmp_path):
    """Silently dropping trades from the statistics is its own defect."""
    trades = [_trade(1.0, 10.0) for _ in range(30)]
    trades += [_trade(1.0, None) for _ in range(5)]
    summary = _run_with(monkeypatch, trades, [0.1] * 30, tmp_path)
    note = " ".join(summary.get("notes") or [])
    assert "5 of 35 trades have no definable capital at risk" in note, note
