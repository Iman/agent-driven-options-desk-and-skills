"""LEAN strategy handoff. Upstream API credit and licences: THIRD-PARTY.md."""
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import shutil


def export_plan(plan, destination, *, start, end, exercise_style, multiplier, data_mode):
    """Export a bounded single-expiry US equity option plan for local LEAN.

    The caller must supply the exercise style, multiplier and data provenance.
    Model premiums are deliberately not used as historical fills.
    """
    if exercise_style != "american" or type(multiplier) is not int or multiplier != 100:
        raise ValueError("evaluation supports American US equity options with multiplier 100 only")
    if data_mode not in ("synthetic", "user-licensed"):
        raise ValueError("data_mode must be synthetic or user-licensed")
    if plan.get("meta", {}).get("degraded"):
        raise ValueError("degraded source plan: " + str(plan["meta"].get("degraded_reason")))
    if plan.get("far_expiry") is not None:
        raise ValueError("time spreads are outside this evaluation")
    symbol = plan.get("underlying", "")
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z]{1,6}", symbol):
        raise ValueError("unsupported underlying ticker")
    expiry = date.fromisoformat(plan["expiry"])
    if not date.fromisoformat(start) < date.fromisoformat(end) <= expiry:
        raise ValueError("require start < end <= expiry")
    legs = []
    for leg in plan.get("legs", []):
        qty, strike = leg.get("qty"), leg.get("strike")
        if (leg.get("kind") not in ("call", "put") or leg.get("side") not in ("long", "short")
                or leg.get("expiry", plan["expiry"]) != plan["expiry"]
                or "days_to_expiry" in leg):
            raise ValueError("only single-expiry option legs with long/short sides are supported")
        if (type(qty) not in (int, float) or not math.isfinite(qty) or qty <= 0 or qty != int(qty)
                or type(strike) not in (int, float) or not math.isfinite(strike) or strike <= 0):
            raise ValueError("require positive integer contracts and finite positive strikes")
        legs.append(dict(kind=leg["kind"], strike=strike,
                         quantity=int(qty) * (1 if leg["side"] == "long" else -1)))
    if not legs:
        raise ValueError("plan has no option legs")
    canonical = json.dumps(plan, sort_keys=True, allow_nan=False).encode()
    bundle = dict(schema_version=1, underlying=symbol, expiry=expiry.isoformat(), start=start, end=end,
                  exercise_style=exercise_style, multiplier=multiplier, data_mode=data_mode,
                  plan_sha256=hashlib.sha256(canonical).hexdigest(), legs=legs)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "plan.json").write_text(json.dumps(bundle, indent=2) + "\n")
    shutil.copyfile(Path(__file__).with_name("lean_algorithm.py"), destination / "main.py")
    return bundle


def summarize_result(result, bundle):
    """Read a final LEAN result, preserving its statistics and excluding host metadata."""
    state = result.get("state", {})
    if state.get("Status") != "Completed" or state.get("RuntimeError"):
        raise ValueError("LEAN result did not complete successfully")
    runtime = result.get("runtimeStatistics", {})
    if runtime.get("OptionDesk Data Mode") != bundle["data_mode"]:
        raise ValueError("LEAN result provenance does not match the exported plan")
    orders = result.get("orders", {})
    # OrderStatus.Filled = 3 in Common/Orders/OrderTypes.cs.
    if not orders or any(order.get("status") != 3 for order in orders.values()):
        raise ValueError("require nonempty, fully filled orders for this evaluation")
    if any(order.get("tag") != "OptionDesk plan sha256: " + bundle["plan_sha256"]
           for order in orders.values()):
        raise ValueError("order provenance does not match the exported plan")
    statistics = result.get("statistics")
    if not isinstance(statistics, dict) or not statistics:
        raise ValueError("missing LEAN statistics")
    return dict(engine="QuantConnect LEAN", data_mode=bundle["data_mode"],
                plan_sha256=bundle["plan_sha256"], filled_orders=len(orders), statistics=statistics,
                interpretation="Synthetic data tests integration only; statistics retain LEAN units.")
