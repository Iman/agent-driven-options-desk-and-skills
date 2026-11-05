"""Explicit exercise-style pricing through the optional QuantLib backend."""
from optiondesk import engine_bridge
from optiondesk.artifacts import DISCLAIMER

FIELDS = ("spot", "strike", "valuation_date", "expiry", "volatility", "rate",
          "dividend_yield", "kind", "exercise_style")


def add_arguments(parser):
    for field in FIELDS:
        numeric = field in ("spot", "strike", "volatility", "rate", "dividend_yield")
        parser.add_argument("--"+field.replace("_", "-"), required=True, type=float if numeric else str)


def run(args):
    result = engine_bridge.quantlib_price({field: getattr(args, field) for field in FIELDS})
    result["disclaimer"] = DISCLAIMER
    return result
