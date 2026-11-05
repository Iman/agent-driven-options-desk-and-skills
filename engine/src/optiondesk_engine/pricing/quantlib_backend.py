"""Optional vanilla pricing. Public requests run in a fresh worker process.

QuantLib contributors retain their modified BSD licence; see THIRD-PARTY.md.
"""
from datetime import date
import json
import math
import subprocess
import sys


def validate_request(payload):
    fields = {"spot", "strike", "valuation_date", "expiry", "volatility", "rate",
              "dividend_yield", "kind", "exercise_style"}
    if set(payload) != fields:
        raise ValueError("pricing requires exactly: " + ", ".join(sorted(fields)))
    for name in ("spot", "strike", "volatility", "rate", "dividend_yield"):
        value = payload[name]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(name + " must be a finite number")
    if min(payload["spot"], payload["strike"], payload["volatility"]) <= 0 or payload["volatility"] > 10:
        raise ValueError("spot, strike and volatility must be positive; volatility must be <= 10")
    if payload["kind"] not in ("call", "put") or payload["exercise_style"] not in ("american", "european"):
        raise ValueError("unsupported option kind or exercise style")
    days = (date.fromisoformat(payload["expiry"]) - date.fromisoformat(payload["valuation_date"])).days
    if not 0 < days <= 36500:
        raise ValueError("expiry must follow valuation date by at most 100 years")
    return payload


def calculate(payload):
    """Worker body; do not share this function across concurrent requests."""
    validate_request(payload)
    try:
        import QuantLib as ql
    except ImportError as exc:
        raise RuntimeError("Install optiondesk-engine[quantlib] to use this backend") from exc
    start = date.fromisoformat(payload["valuation_date"])
    end = date.fromisoformat(payload["expiry"])
    today = ql.Date(start.day, start.month, start.year)
    expiry = ql.Date(end.day, end.month, end.year)
    settings = ql.Settings.instance()
    previous = settings.evaluationDate
    try:
        settings.evaluationDate = today
        dc = ql.Actual365Fixed()
        process = ql.BlackScholesMertonProcess(
            ql.QuoteHandle(ql.SimpleQuote(payload["spot"])),
            ql.YieldTermStructureHandle(ql.FlatForward(today, payload["dividend_yield"], dc)),
            ql.YieldTermStructureHandle(ql.FlatForward(today, payload["rate"], dc)),
            ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), payload["volatility"], dc)))
        payoff = ql.PlainVanillaPayoff(ql.Option.Call if payload["kind"] == "call" else ql.Option.Put, payload["strike"])
        european = ql.VanillaOption(payoff, ql.EuropeanExercise(expiry))
        european.setPricingEngine(ql.AnalyticEuropeanEngine(process))
        reference = european.NPV()
        coarse = fine = reference
        if payload["exercise_style"] == "american":
            option = ql.VanillaOption(payoff, ql.AmericanExercise(today, expiry))
            option.setPricingEngine(ql.FdBlackScholesVanillaEngine(process, 400, 400))
            coarse = option.NPV()
            option.setPricingEngine(ql.FdBlackScholesVanillaEngine(process, 800, 800))
            fine = option.NPV()
        if not all(math.isfinite(v) for v in (fine, coarse, reference)):
            raise ValueError("pricing did not produce finite results")
        difference = abs(fine-coarse)
        degraded = difference > .001
        return dict(backend="QuantLib", backend_version=ql.__version__, price=fine,
                    european_reference=reference, exercise_style=payload["exercise_style"],
                    grid_difference=difference, units="premium per underlying unit", inputs=payload,
                    degraded=degraded, degraded_reason="Grid difference exceeds 0.001 per unit" if degraded else None,
                    assumptions=["Actual/365 Fixed; flat continuous rates and dividend yield; constant volatility.",
                                 "No discrete dividends, transaction costs or contract multiplier.",
                                 "Grid agreement is a convergence check, not an error bound."])
    finally:
        settings.evaluationDate = previous


def price(payload):
    validate_request(payload)
    completed = subprocess.run([sys.executable, "-m", __name__], input=json.dumps(payload),
                               capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "QuantLib worker failed")
    return json.loads(completed.stdout)


if __name__ == "__main__":
    try:
        print(json.dumps(calculate(json.load(sys.stdin)), allow_nan=False))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
