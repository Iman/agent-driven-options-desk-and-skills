"""optiondesk chain: retrieve one option chain and write a snapshot.

Implied volatility is solved from the mid price when the analytics engine is
installed, because a solved volatility is reproducible and the provider's own
is not. Without the engine the provider's published volatility is carried
through instead, labelled as theirs, and the artifact is marked degraded.
Contracts that yield no usable volatility get iv null and are counted.
"""

import argparse
import json

from optiondesk import engine_bridge
from optiondesk.artifacts import envelope, write_json
from optiondesk.contracts import CHAIN_SNAPSHOT, SCHEMA_FILES, validate
from optiondesk.providers import CAP_OPTION_CHAIN, CAP_RISK_FREE_RATE, resolve

IV_MIN = 0.001
IV_MAX = 5.0


def add_arguments(parser):
    """Register the pull options: expiry, provider, risk free rate, dividend
    yield and output directory.
    """
    parser.add_argument("symbol", help="underlying ticker, for example SPY")
    parser.add_argument("--expiry", default=None,
                        help="expiry as YYYY-MM-DD. Default: nearest listed")
    parser.add_argument("--provider", default=None,
                        help="force a provider instead of the registry order")
    parser.add_argument("--rate", type=float, default=None,
                        help="risk-free rate per 1.00. Default: fetched")
    parser.add_argument("--dividend-yield", type=float, default=0.0,
                        dest="dividend_yield",
                        help="continuous dividend yield per 1.00")
    parser.add_argument("--out-dir", default=None,
                        help="artifact directory override")
    return parser


def _solve_iv(engine, contract, spot, t, rate, q):
    """Prefer a solved volatility, fall back to the provider's, else None."""
    mid = contract.get("mid")
    if engine and mid and mid > 0:
        solved = engine["implied_vol"](mid, spot, contract["strike"], t,
                                       contract["type"], rate, q)
        if solved is not None:
            return solved, "solved_mid"
    published = contract.get("iv_provider")
    if published is not None and IV_MIN < published < IV_MAX:
        return float(published), "provider"
    return None, None


def run(args):
    """Pull one option chain, solve implied volatility per contract where the
    price identifies it, and write a snapshot artifact.
    """
    provider, choice = resolve(CAP_OPTION_CHAIN, args.provider)
    quote = provider.underlying_quote(args.symbol)
    chain = provider.option_chain(args.symbol, args.expiry)

    degraded = choice["degraded"]
    reasons = list(choice["skipped"])

    if args.rate is not None:
        rate, rate_source = float(args.rate), "user"
    else:
        rate_provider, _ = resolve(CAP_RISK_FREE_RATE, args.provider)
        fetched = rate_provider.risk_free_rate()
        rate, rate_source = fetched["rate"], fetched["source"]
        if fetched["degraded"]:
            degraded = True
            reasons.append("risk-free rate: " + str(fetched["reason"]))

    engine = None
    if engine_bridge.AVAILABLE:
        engine = engine_bridge.require()
    else:
        degraded = True
        reasons.append(engine_bridge.MISSING_MESSAGE)

    spot = quote["spot"]
    q = float(args.dividend_yield or 0.0)
    t = chain["days_to_expiry"] / 365.0

    with_iv = 0
    from_provider = 0
    from_last_trade = 0
    for contract in chain["contracts"]:
        iv, source = _solve_iv(engine, contract, spot, t, rate, q)
        contract["iv"] = iv
        contract["iv_source"] = source
        if iv is not None:
            with_iv += 1
        if source == "provider":
            from_provider += 1
        if contract.get("mid_source") == "last_trade":
            from_last_trade += 1

    total = len(chain["contracts"])
    without_iv = total - with_iv
    notes = []

    # A published volatility is not a solved one. When a material share of
    # the chain falls back to the provider's own figure, the artifact is
    # lower quality than this pipeline can produce, which is the
    # definition of degraded. Measured at 29.5 percent of a live SPY chain
    # while the artifact reported degraded false.
    if from_provider:
        share = from_provider / total if total else 0.0
        message = ("{} of {} contracts ({:.1%}) use the provider's published "
                   "implied volatility because the solve did not identify "
                   "one".format(from_provider, total, share))
        if share >= 0.05:
            degraded = True
            reasons.append(message)
        else:
            notes.append(message)
    if from_last_trade:
        notes.append(
            "{} of {} contracts have no two-sided quote, so their mid is the "
            "last traded price".format(from_last_trade, total))
    if chain.get("expired"):
        degraded = True
        reasons.append(
            "expiry {} has already passed; time to expiry is floored at a "
            "quarter day and every value derived from it is meaningless"
            .format(chain["expiry"]))
    if without_iv:
        # Not a degradation. Wing contracts with no two-sided quote cannot
        # imply a volatility, and that is what a real chain looks like.
        notes.append(
            "{} of {} contracts have no usable implied volatility and carry "
            "iv null".format(without_iv, len(chain["contracts"])))

    payload = {
        "meta": envelope(
            schema=CHAIN_SNAPSHOT,
            tool="optiondesk chain",
            provider_used=provider.name,
            degraded=degraded,
            degraded_reason="; ".join(reasons) or None,
            inputs={"symbol": args.symbol, "expiry": args.expiry,
                    "rate_source": rate_source,
                    "dividend_yield": q},
            engine_version=engine_bridge.status()["version"],
            notes=notes,
        ),
        "underlying": args.symbol,
        "spot": spot,
        "spot_asof": quote.get("spot_asof"),
        "risk_free_rate": rate,
        "dividend_yield": q,
        "expiry": chain["expiry"],
        "days_to_expiry": chain["days_to_expiry"],
        "contracts": chain["contracts"],
        "counts": {
            "calls": sum(1 for c in chain["contracts"]
                         if c["type"] == "call"),
            "puts": sum(1 for c in chain["contracts"] if c["type"] == "put"),
            "with_iv": with_iv,
            "without_iv": without_iv,
        },
    }
    validate(payload, SCHEMA_FILES[CHAIN_SNAPSHOT])
    filename = "chain_{}_{}.json".format(args.symbol.upper(),
                                         chain["expiry"])
    path = write_json(payload, filename, args.out_dir)
    return {
        "artifact": str(path),
        "underlying": args.symbol,
        "expiry": chain["expiry"],
        "spot": spot,
        "spot_asof": quote.get("spot_asof"),
        "contracts": len(chain["contracts"]),
        "with_iv": with_iv,
        "provider_used": provider.name,
        "degraded": degraded,
        "degraded_reason": payload["meta"]["degraded_reason"],
        "notes": notes,
        "listed_expiries": chain["listed_expiries"][:12],
    }


def main(argv=None):
    """Parse argv for this command alone and run it, so the command works when
    invoked directly as well as through the dispatcher.
    """
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk chain", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1))
    return 0
