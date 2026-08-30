"""optiondesk greeks: full Greek ladder from a chain snapshot.

Reads a snapshot artifact, computes first to third order Greeks with the
engine, and writes a ladder artifact. Every contract uses its own stored
implied volatility. Contracts with iv null are skipped and counted, never
given a default, because a defaulted volatility produces a complete and
entirely fictional ladder that looks exactly as authoritative as a real one.
"""

import argparse
import json

from optiondesk import engine_bridge
from optiondesk.artifacts import envelope, latest, read_json, write_json
from optiondesk.contracts import GREEKS_LADDER, SCHEMA_FILES, validate

# Every field a row carries. The schema promises a consumer never has to
# infer a unit, so a partial list makes that promise false.
UNITS = {
    "price": "model value in the underlying quote currency",
    "delta": "dV/dS per 1.0 of underlying",
    "gamma": "d2V/dS2, delta change per 1.0 of underlying",
    "vega": "dV/dsigma per 1.00 of volatility; divide by 100 for per point",
    "theta": "value change per calendar day; negative is decay",
    "rho": "dV/dr per 1.00 of rate",
    "lam": "elasticity, delta times spot over value; dimensionless",
    "vanna": "d2V/dS dsigma",
    "vomma": "d2V/dsigma2, also called volga",
    "charm": "delta change per calendar day",
    "veta": "vega change per calendar day",
    "speed": "d3V/dS3, gamma change per 1.0 of underlying",
    "zomma": "dGamma/dsigma",
    "color": "gamma change per calendar day",
    "ultima": "d3V/dsigma3",
    "dual_delta": "dV/dK per 1.0 of strike",
    "dual_gamma": "d2V/dK2",
    "iv": "implied volatility per 1.00, so 0.20 is 20 percent",
    "moneyness": "strike divided by spot; dimensionless",
    "days_to_expiry": "calendar days",
}


def add_arguments(parser):
    """Register ladder options: which snapshot, the moneyness band, the option
    type and output directory.
    """
    parser.add_argument("--snapshot", default=None,
                        help="path to a chain snapshot. Default: the most "
                             "recent chain artifact in the artifact dir")
    parser.add_argument("--band", type=float, default=0.10,
                        help="keep strikes within this fraction of spot. "
                             "0 keeps every strike")
    parser.add_argument("--type", default="both",
                        choices=("call", "put", "both"),
                        help="contract type filter")
    parser.add_argument("--out-dir", default=None,
                        help="artifact directory override")
    return parser


def run(args):
    """Compute the sixteen Greek ladder from a snapshot and write a graded
    artifact, skipping contracts whose price identifies no volatility.
    """
    engine = engine_bridge.require()

    path = args.snapshot or latest("chain_*.json", args.out_dir)
    if path is None:
        raise FileNotFoundError(
            "no chain snapshot given and none found. Run 'optiondesk chain "
            "SYMBOL' first, or pass --snapshot PATH.")
    snapshot = read_json(path)

    spot = float(snapshot["spot"])
    # A snapshot without a rate is not an ordinary snapshot. Substituting a
    # constant silently prices every contract off an invented rate and
    # reports rho computed from it, so the substitution is recorded.
    rate_missing = snapshot.get("risk_free_rate") is None
    rate = float(snapshot.get("risk_free_rate") or 0.04)
    q = float(snapshot.get("dividend_yield", 0.0))
    days = float(snapshot["days_to_expiry"])
    t = days / 365.0

    skipped = {"no_iv": 0, "expired": 0, "out_of_band": 0, "error": 0}
    rows = []
    for contract in snapshot["contracts"]:
        if args.type != "both" and contract["type"] != args.type:
            continue
        iv = contract.get("iv")
        if not iv or iv <= 0:
            skipped["no_iv"] += 1
            continue
        if t <= 0:
            skipped["expired"] += 1
            continue
        strike = float(contract["strike"])
        if args.band and abs(strike - spot) > args.band * spot:
            skipped["out_of_band"] += 1
            continue
        try:
            greeks = engine["all_greeks"](spot, strike, t, float(iv),
                                          contract["type"], rate, q)
        except (ValueError, ZeroDivisionError, OverflowError):
            skipped["error"] += 1
            continue
        row = {
            "symbol": contract.get("symbol", ""),
            "type": contract["type"],
            "strike": strike,
            "expiry": snapshot["expiry"],
            "days_to_expiry": days,
            "iv": float(iv),
            "moneyness": strike / spot,
        }
        row.update({key: float(value) for key, value in greeks.items()})
        rows.append(row)
    rows.sort(key=lambda r: (r["type"], r["strike"]))

    source_meta = snapshot.get("meta", {})
    # Degradation is inherited from the snapshot only. Skipping contracts
    # that carry no implied volatility is the correct behaviour, not a
    # defect, so it is recorded as a note and in the skipped counts.
    degraded = bool(source_meta.get("degraded"))
    reasons = []
    if rate_missing:
        degraded = True
        reasons.append(
            "the snapshot carries no risk-free rate, so 0.04 was assumed "
            "and every rho in this ladder is computed from it")
    if source_meta.get("degraded_reason"):
        reasons.append("snapshot: " + str(source_meta["degraded_reason"]))
    notes = list(source_meta.get("notes") or [])
    if skipped["no_iv"]:
        notes.append("{} contracts skipped for having no implied "
                     "volatility".format(skipped["no_iv"]))
    if skipped["out_of_band"]:
        notes.append("{} contracts outside the {} band around spot"
                     .format(skipped["out_of_band"], args.band))
    if skipped["error"]:
        # An engine failure is not routine chain hygiene.
        degraded = True
        reasons.append("{} contracts could not be priced by the engine"
                       .format(skipped["error"]))
    if skipped["expired"]:
        degraded = True
        reasons.append("{} contracts had no time left to expiry"
                       .format(skipped["expired"]))

    payload = {
        "meta": envelope(
            schema=GREEKS_LADDER,
            tool="optiondesk greeks",
            provider_used=source_meta.get("provider_used"),
            degraded=degraded,
            degraded_reason="; ".join(reasons) or None,
            inputs={"snapshot": str(path), "band": args.band,
                    "type": args.type},
            engine_version=engine["version"],
            notes=notes,
        ),
        "source_artifact": str(path),
        "underlying": snapshot["underlying"],
        "expiry": snapshot.get("expiry"),
        "days_to_expiry": days,
        "spot": spot,
        "risk_free_rate": rate,
        "dividend_yield": q,
        "units": UNITS,
        "skipped": skipped,
        "rows": rows,
    }
    validate(payload, SCHEMA_FILES[GREEKS_LADDER])
    filename = "greeks_{}_{}.json".format(
        str(snapshot["underlying"]).upper(), snapshot["expiry"])
    out = write_json(payload, filename, args.out_dir)

    atm = min(rows, key=lambda r: abs(r["strike"] - spot), default=None)
    return {
        "artifact": str(out),
        "underlying": snapshot["underlying"],
        "expiry": snapshot["expiry"],
        "spot": spot,
        "rows": len(rows),
        "skipped": skipped,
        "engine_version": engine["version"],
        "degraded": degraded,
        "degraded_reason": payload["meta"]["degraded_reason"],
        "notes": notes,
        "atm_sample": {k: atm[k] for k in
                       ("strike", "type", "iv", "price", "delta", "gamma",
                        "vega", "theta")} if atm else None,
    }


def main(argv=None):
    """Parse argv for this command alone and run it, so the command works when
    invoked directly as well as through the dispatcher.
    """
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk greeks", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1))
    return 0
