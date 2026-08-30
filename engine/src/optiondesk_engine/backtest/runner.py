"""Run a structure repeatedly across a price history.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.

THE LOOP. Every entry_every trading days, build the structure from a
synthetic chain priced at the volatility estimated from the trailing window,
hold it to expiry, and settle it against the underlying's actual close on
that date. Real path, modelled premium. Read the honesty rule in the package
docstring before using any number this produces.

WHY A SYNTHETIC CHAIN. No history of quotes exists, so strikes are generated
around the spot of the day and priced with the engine's own model. The
consequence is specific and worth stating plainly: entry and exit premiums
are internally consistent with the model, which means the backtest cannot
discover any edge that comes from the market mispricing options relative to
that model. What it can measure is the payoff geometry of a structure
against the real distribution of underlying moves, which is a narrower but
honest question.

VOLATILITY ESTIMATE. Trailing realised volatility over a lookback window, so
the entry premium reflects what was knowable that day. Using the volatility
realised over the holding period instead would be lookahead, and would make
every short-premium structure look profitable.
"""

import math

TRADING_DAYS = 252
DEFAULT_LOOKBACK = 60


def realised_volatility(returns):
    """Annualised volatility from log returns, or None if too few."""
    if len(returns) < 20:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance * TRADING_DAYS)


def synthetic_chain(bs_price, spot, days, volatility, rate=0.04,
                    dividend_yield=0.0, width=0.25, step=0.01):
    """A chain of strikes around spot, priced by the model.

    Strikes run to width either side of spot in steps of step, as fractions
    of spot, which is close enough to how listed strikes are spaced for the
    structures here to find what they need.
    """
    t = days / 365.0
    contracts = []
    count = int(width / step)
    for index in range(-count, count + 1):
        strike = round(spot * (1.0 + index * step), 2)
        if strike <= 0:
            continue
        for kind in ("call", "put"):
            try:
                price = bs_price(spot, strike, t, volatility, kind, rate,
                                 dividend_yield)
            except (ValueError, ZeroDivisionError, OverflowError):
                continue
            if price <= 0:
                continue
            contracts.append({
                "symbol": "SYN{}{}".format(kind[0].upper(), strike),
                "type": kind, "strike": strike,
                "bid": price, "ask": price, "mid": price,
                "iv": volatility, "iv_source": "model",
                "open_interest": 1000, "volume": 100,
            })
    return {"underlying": "SYNTHETIC", "spot": spot, "expiry": None,
            "days_to_expiry": days, "contracts": contracts,
            "risk_free_rate": rate, "dividend_yield": dividend_yield}


def run_backtest(strategies, bs_price, prices, dates, strategy_name,
                 holding_days=30, entry_every=5, lookback=DEFAULT_LOOKBACK,
                 rate=0.04, dividend_yield=0.0, size=1.0):
    """Enter a structure repeatedly and settle each one at expiry.

    Returns every trade, the per-trade returns on capital at risk, and the
    reasons any entry was skipped. A skipped entry is recorded rather than
    silently dropped, because a rule that only trades when conditions are
    perfect has a different meaning from one that trades every week.
    """
    if len(prices) != len(dates):
        raise ValueError("prices and dates must be the same length")
    if len(prices) < lookback + holding_days + 5:
        raise ValueError(
            "need at least {} closes for a {} day hold with a {} day "
            "lookback, got {}".format(lookback + holding_days + 5,
                                      holding_days, lookback, len(prices)))

    log_returns = []
    for previous, current in zip(prices, prices[1:]):
        log_returns.append(math.log(current / previous)
                           if previous > 0 and current > 0 else 0.0)

    trades = []
    skipped = []
    index = lookback
    while index + holding_days < len(prices):
        spot = prices[index]
        window = log_returns[index - lookback:index]
        volatility = realised_volatility(window)
        if not volatility or volatility <= 0:
            skipped.append({"date": dates[index],
                            "reason": "no volatility estimate"})
            index += entry_every
            continue

        chain = strategies.split_chain(
            synthetic_chain(bs_price, spot, holding_days, volatility, rate,
                            dividend_yield))
        try:
            plan = strategies.build(strategy_name, chain, size=size)
        except (KeyError, NotImplementedError) as exc:
            raise ValueError(str(exc)) from exc
        if plan is None:
            skipped.append({"date": dates[index],
                            "reason": "no viable structure at this "
                                      "volatility"})
            index += entry_every
            continue

        settle = prices[index + holding_days]
        profit = strategies.pnl_at_expiry(plan["legs"], settle)
        analysis = plan["analysis"]
        max_loss = analysis["max_loss"]
        capital = (abs(max_loss)
                   if isinstance(max_loss, (int, float))
                   and max_loss not in (float("-inf"),) else None)

        trades.append({
            "entry_date": dates[index],
            "exit_date": dates[index + holding_days],
            "entry_spot": spot,
            "exit_spot": settle,
            "underlying_return": settle / spot - 1.0,
            "entry_volatility": volatility,
            "net_cash": analysis["net_cash"],
            "trade_type": analysis["trade_type"],
            "capital_at_risk": capital,
            "profit": profit,
            "return_on_risk": (profit / capital) if capital else None,
            "breakevens": analysis["breakevens"],
            "legs": [leg.as_dict() for leg in plan["legs"]],
        })
        index += entry_every

    returns = [t["return_on_risk"] for t in trades
               if t["return_on_risk"] is not None]
    return {
        "strategy": strategy_name,
        "trades": trades,
        "returns": returns,
        "skipped": skipped,
        "settings": {
            "holding_days": holding_days,
            "entry_every": entry_every,
            "lookback": lookback,
            "rate": rate,
            "dividend_yield": dividend_yield,
            "size": size,
            "first_date": dates[0],
            "last_date": dates[-1],
        },
        "premium_source": "model",
        "honesty": (
            "Underlying closes are real. Option premiums are Black-Scholes "
            "values at trailing realised volatility, not quotes and not "
            "fills. There is no spread, no slippage, no assignment and no "
            "early exercise. Entry and exit are priced by the same model, "
            "so this cannot detect any edge arising from the market "
            "disagreeing with that model. It measures a structure's payoff "
            "geometry against real moves, and nothing more."),
    }
