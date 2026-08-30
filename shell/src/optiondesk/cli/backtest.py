"""optiondesk backtest: a structure entered repeatedly across real history.

Real underlying closes, modelled premiums. Read the honesty field in the
output before quoting any number from it, and read it again before showing
anyone else.

Alongside the performance statistics, this reports a permutation test and a
bootstrap interval, because a mean return without a statement of how easily
it could have arisen by chance is not a result. It also runs the same rule
against the underlying itself, so a structure that merely tracks the market
is visible as such rather than being credited with the market's move.
"""

import argparse
import json

from optiondesk import engine_bridge
from optiondesk.artifacts import envelope, write_json
from optiondesk.contracts import BACKTEST, SCHEMA_FILES, validate
from optiondesk.providers import CAP_UNDERLYING_HISTORY, resolve


def add_arguments(parser):
    """Register the window and cadence: holding days, entry interval, lookback,
    history period, rate, dividend yield, size, provider and output directory.
    """
    parser.add_argument("symbol", help="underlying ticker")
    parser.add_argument("strategy", help="structure to test, for example "
                                         "iron_condor")
    parser.add_argument("--holding-days", type=int, default=30,
                        dest="holding_days",
                        help="days from entry to expiry")
    parser.add_argument("--entry-every", type=int, default=5,
                        dest="entry_every",
                        help="trading days between entries")
    parser.add_argument("--lookback", type=int, default=60,
                        help="window for the trailing volatility estimate")
    parser.add_argument("--period", default="5y",
                        help="how much history to test, for example 5y")
    parser.add_argument("--rate", type=float, default=0.04,
                        help="risk-free rate per 1.00 used for pricing")
    parser.add_argument("--dividend-yield", type=float, default=0.0,
                        dest="dividend_yield")
    parser.add_argument("--size", type=float, default=1.0,
                        help="contracts per leg")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--out-dir", default=None)
    return parser


def _benchmark(prices, dates, holding_days, entry_every, lookback,
               engine_backtest):
    """The same schedule, holding the underlying instead of the structure.

    Without this, a structure that is simply long the market gets credit
    for the market's drift and looks like a strategy.
    """
    returns = []
    index = lookback
    while index + holding_days < len(prices):
        entry, exit_price = prices[index], prices[index + holding_days]
        if entry > 0:
            returns.append(exit_price / entry - 1.0)
        index += entry_every
    stats = engine_backtest.performance_stats(returns, holding_days)
    if stats:
        stats.pop("equity_curve", None)
    return {"description": ("buy and hold the underlying over the same "
                            "windows, for comparison"),
            "statistics": stats}


def run(args):
    """Enter one structure repeatedly across real history and write a backtest
    artifact with its honesty statement attached.
    """
    engine = engine_bridge.require()
    strategies = engine_bridge.strategies()
    engine_backtest = engine_bridge.backtest()

    provider, choice = resolve(CAP_UNDERLYING_HISTORY, args.provider)
    history = provider.underlying_history(args.symbol, period=args.period)

    result = engine_backtest.run_backtest(
        strategies, engine["bs_price"], history["closes"], history["dates"],
        args.strategy, holding_days=args.holding_days,
        entry_every=args.entry_every, lookback=args.lookback,
        rate=args.rate, dividend_yield=args.dividend_yield, size=args.size)

    returns = result["returns"]
    statistics = engine_backtest.performance_stats(returns,
                                                   args.holding_days)
    significance = engine_backtest.permutation_p_value(returns)
    interval = engine_backtest.bootstrap_mean_interval(returns)
    benchmark = _benchmark(history["closes"], history["dates"],
                           args.holding_days, args.entry_every,
                           args.lookback, engine_backtest)

    notes = []
    if len(returns) < 30:
        notes.append("only {} trades: too few for any statistic here to "
                     "carry weight".format(len(returns)))
    if result["skipped"]:
        notes.append("{} entries skipped, mostly where no viable structure "
                     "existed at that volatility".format(
                         len(result["skipped"])))
    if significance and significance["p_value"] > 0.05:
        notes.append("the permutation test cannot distinguish this result "
                     "from a rule with no edge")

    equity_curve = (statistics or {}).pop("equity_curve", None)

    payload = {
        "meta": envelope(
            schema=BACKTEST,
            tool="optiondesk backtest",
            provider_used=provider.name,
            degraded=bool(choice["degraded"]),
            degraded_reason="; ".join(choice["skipped"]) or None,
            inputs={"symbol": args.symbol, "strategy": args.strategy,
                    "holding_days": args.holding_days,
                    "entry_every": args.entry_every,
                    "period": args.period},
            engine_version=engine["version"],
            notes=notes,
        ),
        "underlying": args.symbol.upper(),
        "strategy": args.strategy,
        "premium_source": result["premium_source"],
        "honesty": result["honesty"],
        "settings": dict(result["settings"], equity_curve=equity_curve),
        "statistics": statistics,
        "significance": significance,
        "interval": interval,
        "benchmark": benchmark,
        "trades": result["trades"],
        "skipped": result["skipped"],
    }
    validate(payload, SCHEMA_FILES[BACKTEST])
    filename = "backtest_{}_{}_{}d.json".format(
        args.symbol.upper(), args.strategy, args.holding_days)
    out = write_json(payload, filename, args.out_dir)

    return {
        "artifact": str(out),
        "underlying": args.symbol.upper(),
        "strategy": args.strategy,
        "degraded": bool(choice["degraded"]),
        "degraded_reason": "; ".join(choice["skipped"]) or None,
        "trades": (statistics or {}).get("trades", 0),
        "win_rate": (statistics or {}).get("win_rate"),
        "mean_return_on_risk": (statistics or {}).get("mean_return"),
        "total_return_on_risk": (statistics or {}).get(
            "total_return_on_risk"),
        "max_drawdown_in_risk_units": (statistics or {}).get(
            "max_drawdown_in_risk_units"),
        "sharpe_per_trade": (statistics or {}).get("sharpe_per_trade"),
        "p_value": (significance or {}).get("p_value"),
        "mean_interval": ([interval["lower"], interval["upper"]]
                          if interval else None),
        "interval_excludes_zero": (interval or {}).get("excludes_zero"),
        "benchmark_mean": ((benchmark["statistics"] or {}).get("mean_return")
                           if benchmark["statistics"] else None),
        "skipped_entries": len(result["skipped"]),
        "notes": notes,
        "honesty": result["honesty"],
    }


def main(argv=None):
    """Parse argv for this command alone and run it, so the command works when
    invoked directly as well as through the dispatcher.
    """
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk backtest", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1, default=str))
    return 0
