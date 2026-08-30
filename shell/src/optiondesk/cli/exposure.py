"""optiondesk exposure: positioning and volatility geometry for a chain.

Computes dealer gamma exposure by strike, the call and put walls, the
estimated gamma flip level, max pain, put-call ratios and the smile
geometry a volatility trader quotes: at-the-money volatility, 25-delta risk
reversal, butterfly, skew slope and the implied expected move.

Unlike the Greek ladder this runs across the whole chain rather than a band
around spot, because a wall three hundred points away is exactly the thing
a band would hide.

Every number rests on the sign convention stated in the artifact: dealers
long calls and short puts. That is the market convention and it is often
wrong for a single name. Read the assumption before quoting the walls.
"""

import argparse
import json

from optiondesk import engine_bridge
from optiondesk.artifacts import envelope, latest, read_json, write_json
from optiondesk.contracts import EXPOSURE, SCHEMA_FILES, validate

CONTRACT_MULTIPLIER = 100.0


def add_arguments(parser):
    parser.add_argument("--snapshot", default=None,
                        help="chain snapshot path. Default: most recent")
    parser.add_argument("--multiplier", type=float,
                        default=CONTRACT_MULTIPLIER,
                        help="contract multiplier, 100 for US equity options")
    parser.add_argument("--out-dir", default=None,
                        help="artifact directory override")
    return parser


def run(args):
    engine = engine_bridge.require()
    analytics = engine_bridge.analytics()

    path = args.snapshot or latest("chain_*.json", args.out_dir)
    if path is None:
        raise FileNotFoundError(
            "no chain snapshot given and none found. Run 'optiondesk chain "
            "SYMBOL' first, or pass --snapshot PATH.")
    snapshot = read_json(path)

    spot = float(snapshot["spot"])
    days = float(snapshot["days_to_expiry"])
    rate = float(snapshot.get("risk_free_rate") or 0.04)
    dividend_yield = float(snapshot.get("dividend_yield") or 0.0)
    t = days / 365.0

    # Gamma for every contract that carries a volatility. This is the whole
    # chain, not a band: the walls are usually outside any sensible band.
    priced = []
    without_iv = 0
    for contract in snapshot["contracts"]:
        iv = contract.get("iv")
        if not iv or iv <= 0 or t <= 0:
            without_iv += 1
            priced.append(dict(contract, gamma=None, delta=None))
            continue
        try:
            greeks = engine["all_greeks"](spot, float(contract["strike"]), t,
                                          float(iv), contract["type"], rate,
                                          dividend_yield)
        except (ValueError, ZeroDivisionError, OverflowError):
            without_iv += 1
            priced.append(dict(contract, gamma=None, delta=None))
            continue
        priced.append(dict(contract, gamma=greeks["gamma"],
                           delta=greeks["delta"]))

    exposure = analytics.chain_exposure(priced, spot, args.multiplier)
    pain = analytics.max_pain(priced, args.multiplier)
    smile = analytics.smile_metrics(priced, spot, days)

    source_meta = snapshot.get("meta", {})
    notes = list(source_meta.get("notes") or [])
    if without_iv:
        notes.append("{} contracts carry no usable implied volatility and "
                     "are excluded from the exposure profile"
                     .format(without_iv))
    if exposure["skipped"]:
        notes.append("{} contracts have no open interest recorded and are "
                     "excluded rather than counted as zero"
                     .format(exposure["skipped"]))

    payload = {
        "meta": envelope(
            schema=EXPOSURE,
            tool="optiondesk exposure",
            provider_used=source_meta.get("provider_used"),
            degraded=bool(source_meta.get("degraded")),
            degraded_reason=source_meta.get("degraded_reason"),
            inputs={"snapshot": str(path), "multiplier": args.multiplier},
            engine_version=engine["version"],
            notes=notes,
        ),
        "source_artifact": str(path),
        "underlying": snapshot["underlying"],
        "spot": spot,
        "expiry": snapshot.get("expiry"),
        "days_to_expiry": days,
        "exposure": exposure,
        "max_pain": pain,
        "smile": smile,
    }
    validate(payload, SCHEMA_FILES[EXPOSURE])
    filename = "exposure_{}_{}.json".format(
        str(snapshot["underlying"]).upper(), snapshot["expiry"])
    out = write_json(payload, filename, args.out_dir)

    return {
        "artifact": str(out),
        "underlying": snapshot["underlying"],
        "expiry": snapshot.get("expiry"),
        "spot": spot,
        "net_gex": exposure["net_gex"],
        "regime": exposure["regime"],
        "gamma_flip": exposure["gamma_flip"],
        "call_wall": exposure["call_wall"],
        "put_wall": exposure["put_wall"],
        "put_call_oi_ratio": exposure["put_call_oi_ratio"],
        "max_pain": pain["strike"] if pain else None,
        "atm_iv": smile["atm_iv"] if smile else None,
        "risk_reversal_25d": smile["risk_reversal"] if smile else None,
        "butterfly_25d": smile["butterfly"] if smile else None,
        "expected_move": smile["expected_move"] if smile else None,
        "notes": notes,
        "assumption": exposure["assumption"],
    }


def main(argv=None):
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk exposure", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1, default=str))
    return 0
