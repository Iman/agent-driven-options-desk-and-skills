"""optiondesk simulate: what the underlying's own behaviour implies.

Fits a Bayesian GARCH(1,1)-t model to the underlying's realised returns by
MCMC, simulates the forward distribution with one posterior draw per path,
and reports the fan, the tail risk, and the profit distribution of every
structure already built for that underlying.

This is deliberately a second opinion. The strategy probabilities elsewhere
come from the volatility the options are priced at; these come from the
volatility the underlying has actually shown. When the two disagree, the
disagreement is the information, and neither one is the truth.

Convergence is reported, never assumed. If the chains have not agreed, the
quantiles are still written, and the artifact says plainly that they should
not be quoted.
"""

import argparse
import json
import sys
import math

from pathlib import Path

from optiondesk import engine_bridge
from optiondesk.artifacts import artifact_dir, envelope, read_json, write_json
from optiondesk.contracts import SCHEMA_FILES, SIMULATION, validate
from optiondesk.providers import CAP_UNDERLYING_HISTORY, resolve

TRADING_DAYS = 252


def add_arguments(parser):
    """Register simulation controls: horizon, path count, draws, burn-in, chain
    count, history period, provider, whether to price structures and output
    directory.
    """
    parser.add_argument("symbol", help="underlying ticker")
    parser.add_argument("--horizon", type=int, default=5,
                        help="business days to simulate forward")
    parser.add_argument("--paths", type=int, default=20000,
                        help="simulated paths, in antithetic pairs")
    parser.add_argument("--draws", type=int, default=3000,
                        help="posterior draws per chain after burn-in")
    parser.add_argument("--burn", type=int, default=1000,
                        help="burn-in iterations per chain")
    parser.add_argument("--chains", type=int, default=2,
                        help="independent chains, for the R-hat diagnostic")
    parser.add_argument("--period", default="2y",
                        help="how much history to fit, for example 2y or 5y")
    parser.add_argument("--provider", default=None,
                        help="force a provider instead of the registry order")
    parser.add_argument("--no-structures", action="store_true",
                        dest="no_structures",
                        help="skip the profit distribution of saved plans")
    parser.add_argument("--out-dir", default=None,
                        help="artifact directory override")
    return parser


def _legs_from_plan(strategies, plan):
    """Rebuild engine legs from a saved plan so its payoff can be evaluated."""
    legs = []
    for leg in plan.get("legs", []):
        legs.append(strategies.Leg(
            leg["kind"],
            1 if leg["side"] == "long" else -1,
            float(leg["price"]),
            strike=leg.get("strike"),
            qty=float(leg.get("qty", 1.0)),
        ))
    return legs


# Measured, not guessed: 18 core arm64, 1253 observations, python 3.13.
# draws 3000 burn 1000 chains 2 took 7.9 seconds end to end including the
# history fetch, and draws 6000 burn 2000 chains 4 took 26.7. That is about
# 1.6 microseconds per iteration-observation, and it is the only number
# behind the estimate below.
SECONDS_PER_ITERATION_OBSERVATION = 1.6e-6


def _rough_duration(iterations, observations):
    """A human-sized estimate of the sampler's run time.

    Deliberately vague above a minute. The constant was measured on one
    machine, the work is linear in iterations times observations, and a
    number with two decimal places would imply a precision this cannot
    have. The purpose is only to stop someone killing a run that is
    working.
    """
    seconds = iterations * observations * SECONDS_PER_ITERATION_OBSERVATION
    if seconds < 20:
        return "a few seconds"
    if seconds < 90:
        return "under a minute"
    if seconds < 600:
        return "a few minutes"
    return "ten minutes or more"


def run(args):
    """Fit the GARCH(1,1)-t posterior by MCMC, simulate paths from it and write
    a simulation artifact carrying its own convergence verdict.
    """
    engine = engine_bridge.require()
    sim_module = engine_bridge.simulation()
    strategies = engine_bridge.strategies()

    provider, choice = resolve(CAP_UNDERLYING_HISTORY, args.provider)
    history = provider.underlying_history(args.symbol, period=args.period)
    returns = history["returns"]
    spot = history["last_close"]

    # Say what is about to happen, before it happens, on stderr so it never
    # lands in the JSON a caller is parsing. The sampler is pure Python and
    # single threaded: it walks (draws + burn) x chains iterations over
    # every observation, with no vectorisation and no C extension. On an
    # eighteen core arm64 machine with 1253 observations the default
    # settings take about eight seconds and the heaviest sensible ones
    # about twenty seven. A slower or single core machine can be several
    # times that, and it looks identical to a hang: no output, no progress,
    # one busy core. Anyone who kills it there loses the run and concludes
    # the tool is broken.
    iterations = (args.draws + args.burn) * args.chains
    print("Fitting {} chains of {} draws after {} burn-in, {} iterations "
          "over {} observations. The sampler is single threaded and prints "
          "nothing until it finishes. Roughly {} on a machine like the one "
          "this was measured on; slower hardware takes proportionally "
          "longer. Let it run.".format(
              args.chains, args.draws, args.burn, iterations, len(returns),
              _rough_duration(iterations, len(returns))),
          file=sys.stderr)

    posterior = sim_module.fit_garch_t(returns, draws=args.draws,
                                       burn=args.burn, chains=args.chains)
    simulation = sim_module.simulate_paths(posterior, spot, args.horizon,
                                           paths=args.paths)
    # Both can now refuse: the simulator raises when every path is
    # non-finite, and the risk summary returns None rather than reporting a
    # probability of an up move computed from NaN comparisons.
    risk = sim_module.terminal_risk(simulation)

    degraded = bool(choice["degraded"])
    reasons = list(choice["skipped"])
    notes = []
    if risk is None:
        degraded = True
        reasons.append(
            "the simulated distribution is not finite, so no value at risk "
            "or expected shortfall could be computed")
    elif risk.get("insufficient_paths"):
        degraded = True
        reasons.extend(risk["insufficient_paths"])
    if simulation.get("discarded_paths"):
        notes.append("{} of {} requested paths were discarded as "
                     "non-finite".format(simulation["discarded_paths"],
                                         simulation["requested_paths"]))
    if not posterior.converged:
        degraded = True
        reasons.append(
            "the sampler has not converged: " + posterior.diagnostics["note"])

    structures = []
    if not args.no_structures:
        # Plans are read straight from disk rather than through any
        # group index, because a group keeps only the newest artifact of
        # each kind and there is one plan per structure.
        directory = Path(args.out_dir) if args.out_dir else artifact_dir()
        for path in sorted(directory.glob("strategy_{}_*.json".format(
                args.symbol.upper()))):
            try:
                plan = read_json(path)
            except (ValueError, OSError):
                continue
            if not isinstance(plan, dict):
                continue
            legs = _legs_from_plan(strategies, plan)
            if not legs:
                continue
            distribution = sim_module.position_distribution(
                simulation,
                lambda price, legs=legs: strategies.pnl_at_expiry(legs, price))
            model_probability = (plan.get("probability") or {}).get("profit")
            structures.append({
                "strategy": plan.get("strategy"),
                "expiry": plan.get("expiry"),
                "artifact": str(path),
                "realised_vol_probability_of_profit":
                    distribution["probability_of_profit"],
                "implied_vol_probability_of_profit": model_probability,
                "disagreement": (
                    distribution["probability_of_profit"] - model_probability
                    if model_probability is not None else None),
                "mean": distribution["mean"],
                "median": distribution["median"],
                "p5": distribution["p5"],
                "p95": distribution["p95"],
                "expected_shortfall_5": distribution["expected_shortfall_5"],
                "worst": distribution["worst"],
                "best": distribution["best"],
                "histogram": distribution["histogram"],
            })
        if structures:
            notes.append(
                "structure probabilities are computed from realised "
                "volatility and will differ from the implied-volatility "
                "figures on the plans themselves")

    daily_variance = sum(r * r for r in returns) / len(returns)
    payload = {
        "meta": envelope(
            schema=SIMULATION,
            tool="optiondesk simulate",
            provider_used=provider.name,
            degraded=degraded,
            degraded_reason="; ".join(reasons) or None,
            inputs={"symbol": args.symbol, "horizon": args.horizon,
                    "paths": args.paths, "draws": args.draws,
                    "chains": args.chains, "period": args.period},
            engine_version=engine["version"],
            notes=notes,
        ),
        "underlying": args.symbol.upper(),
        "spot": spot,
        "history": {
            "observations": len(returns),
            "first": history["first"],
            "last": history["last"],
            "period": history["period"],
            "annualised_volatility": math.sqrt(daily_variance * TRADING_DAYS),
        },
        "posterior": {
            "converged": posterior.converged,
            "model": ("GARCH(1,1) with standardised Student-t innovations, "
                      "sampled by adaptive random-walk Metropolis"),
            "parameters": posterior.summary(),
            "diagnostics": posterior.diagnostics,
        },
        "simulation": {
            "horizon_days": simulation["horizon_days"],
            "paths": simulation["paths"],
            # Requested as well as kept. The engine returns both and this
            # block carried only the kept count, so the dashboard's maths
            # panel, which prints "requested (kept)", fell back to the
            # engine default and described a 5,000-path run as 20,000.
            "requested_paths": simulation["requested_paths"],
            "antithetic": simulation["antithetic"],
            "fan": simulation["fan"],
            "terminal_histogram": _histogram(simulation["terminal"]),
        },
        "risk": risk,
        "structures": structures,
    }
    validate(payload, SCHEMA_FILES[SIMULATION])
    filename = "simulation_{}_{}d.json".format(args.symbol.upper(),
                                               args.horizon)
    out = write_json(payload, filename, args.out_dir)

    summary = posterior.summary()
    return {
        "artifact": str(out),
        "underlying": args.symbol.upper(),
        "spot": spot,
        "degraded": degraded,
        "degraded_reason": "; ".join(reasons) or None,
        "history_observations": len(returns),
        "annualised_volatility": payload["history"]["annualised_volatility"],
        "converged": posterior.converged,
        "acceptance_rate": posterior.diagnostics["acceptance_rate"],
        "min_effective_sample_size": min(
            posterior.diagnostics["ess"].values()),
        "max_rhat": _max_rhat(posterior.diagnostics["rhat"]),
        "persistence": summary["alpha"]["p50"] + summary["beta"]["p50"],
        "degrees_of_freedom": summary["nu"]["p50"],
        "horizon_days": args.horizon,
        "paths": simulation["paths"],
        "terminal_p5": simulation["fan"][-1]["p5"],
        "terminal_p50": simulation["fan"][-1]["p50"],
        "terminal_p95": simulation["fan"][-1]["p95"],
        "var_95": risk["var_95"] if risk else None,
        "es_95": risk["es_95"] if risk else None,
        "structures": [
            {"strategy": s["strategy"],
             "realised": s["realised_vol_probability_of_profit"],
             "implied": s["implied_vol_probability_of_profit"],
             "disagreement": s["disagreement"]}
            for s in structures],
        "notes": notes,
    }


def _max_rhat(rhat):
    """The worst R-hat, or None when none could be computed.

    Every value is None when the chains are too short to split, and max()
    over an empty generator raised after the artifact had already been
    written, so the command reported failure while leaving a complete file
    on disk for the dashboard to read.
    """
    values = [v for v in rhat.values() if v is not None]
    return max(values) if values else None


def _histogram(values, bins=48):
    if not values:
        return []
    low, high = values[0], values[-1]
    if high <= low:
        return [{"lo": low, "hi": high, "count": len(values)}]
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        counts[min(bins - 1, int((value - low) / width))] += 1
    return [{"lo": low + i * width, "hi": low + (i + 1) * width,
             "count": counts[i]} for i in range(bins)]


def main(argv=None):
    """Parse argv for this command alone and run it, so the command works when
    invoked directly as well as through the dispatcher.
    """
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk simulate", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1, default=str))
    return 0
