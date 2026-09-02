"""optiondesk chain: retrieve one option chain and write a snapshot.

Implied volatility is solved from the mid price when the analytics engine is
installed, because a solved volatility is reproducible and the provider's own
is not. Without the engine the provider's published volatility is carried
through instead, labelled as theirs, and the artifact is marked degraded.
Contracts that yield no usable volatility get iv null and are counted.
"""

import argparse
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace

from optiondesk import engine_bridge
from optiondesk.artifacts import envelope, write_json
from optiondesk.contracts import CHAIN_SNAPSHOT, SCHEMA_FILES, validate
from optiondesk.providers import (
    CAP_DIVIDEND_YIELD,
    CAP_OPTION_CHAIN,
    CAP_RISK_FREE_RATE,
    resolve,
)

IV_MIN = 0.001
IV_MAX = 5.0
MAX_USER_DATA_BYTES = 2_000_000
MAX_USER_ROWS = 20_000

_TRUE_NULLS = {"", "na", "n/a", "none", "null", "nil"}
_TYPE_ALIASES = {
    "call": "call",
    "calls": "call",
    "c": "call",
    "put": "put",
    "puts": "put",
    "p": "put",
}


def snapshot_schema():
    """Describe the private user-data contract for agent clients."""
    return {
        "purpose": "private user-supplied option-chain analysis",
        "accepted_inputs": [
            "source_data: a JSON object with contracts or rows",
            "source_text: CSV or JSON text with source_format",
            "source_path: a local CSV or JSON path",
        ],
        "required_metadata": ["symbol", "spot", "expiry", "data_source"],
        "recommended_metadata": [
            "snapshot_timestamp", "risk_free_rate", "dividend_yield"],
        "required_contract_fields": ["strike", "type"],
        "recommended_contract_fields": [
            "bid", "ask", "implied_volatility", "volume",
            "open_interest"],
        "aliases": {
            "type": ["type", "call_put", "option_type", "right", "cp"],
            "strike": ["strike", "strike_price", "strikeprice"],
            "implied_volatility": [
                "iv", "implied_volatility", "implied vol", "sigma"],
            "open_interest": ["open_interest", "openinterest", "oi"],
        },
        "repair_policy": (
            "Normalize column aliases, call or put notation, numeric commas, "
            "and clear percentage units. Never invent a missing strike, "
            "option type, spot, expiry, quote, or source."),
        "rights": (
            "Set rights_confirmed true only after the user states that the "
            "data can be sent for private analysis. This statement does not "
            "grant public display or redistribution rights."),
        "limits": {"bytes": MAX_USER_DATA_BYTES, "rows": MAX_USER_ROWS},
    }


def _to_float(value):
    """Parse one optional number from a string or number input.

    Accept blank or NA-like cells as None, because CSV snapshots often use
    those for stale or unavailable fields.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("number must be finite, got {!r}".format(value))
        return number
    text = str(value).strip()
    if not text or text.lower() in _TRUE_NULLS:
        return None
    number = float(text.replace(",", ""))
    if not math.isfinite(number):
        raise ValueError("number must be finite, got {!r}".format(value))
    return number


def _to_int(value):
    """Parse one optional integer field safely.

    Float strings become int where they are exact, because some providers
    serialize contract-size fields as floats in CSV.
    """
    value = _to_float(value)
    if value is None:
        return None
    if not value.is_integer():
        raise ValueError("expected a whole number, got {!r}".format(value))
    return int(value)


def _first(data, *candidates):
    """Return the first present key from candidates, case-insensitively."""
    if not isinstance(data, dict):
        return None
    lookup = {str(key).strip().lower(): value for key, value in data.items()}
    for candidate in candidates:
        for key in (candidate, candidate.replace("-", "_")):
            value = lookup.get(str(key).strip().lower())
            if value is not None:
                return value
    return None


def _parse_option_type(value):
    """Accept call/put notation across common snapshot variants."""
    if value is None:
        raise ValueError("missing option type")
    normalized = str(value).strip().lower()
    if normalized not in _TYPE_ALIASES:
        raise ValueError("unknown option type {!r}".format(value))
    return _TYPE_ALIASES[normalized]


def _days_to_expiry(expiry):
    """Derive DTE from an expiry string.

    DTE is a number in the schema and can be fractional if markets settle
    around midnight in non-UTC timezones.
    """
    expiry_dt = datetime.fromisoformat(expiry)
    today = datetime.now(timezone.utc).date()
    return (expiry_dt.date() - today).days


def _rows_from_payload(payload):
    """Split one JSON value into metadata and contract rows."""
    if isinstance(payload, dict):
        if "contracts" in payload:
            contracts = payload["contracts"]
            if not isinstance(contracts, list):
                raise ValueError("contracts must be a list in JSON input")
            return payload, contracts
        if "rows" in payload:
            rows = payload["rows"]
            if not isinstance(rows, list):
                raise ValueError("rows must be a list in JSON input")
            return payload, rows
    elif isinstance(payload, list):
        return {}, payload

    raise ValueError("unsupported JSON snapshot shape: {}".format(type(payload)))


def _nonempty_csv_rows(text):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV input has no header row")
    return [row for row in reader if any(
        value is not None and str(value).strip() for value in row.values())]


def _read_chain_snapshot_text(text, source_format):
    """Read an inline CSV or JSON snapshot without a temporary file."""
    if not isinstance(text, str):
        raise ValueError("inline snapshot text must be a string")
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_USER_DATA_BYTES:
        raise ValueError(
            "inline snapshot is {} bytes; the limit is {} bytes".format(
                len(encoded), MAX_USER_DATA_BYTES))
    kind = str(source_format or "").strip().lower()
    if kind not in ("csv", "json"):
        raise ValueError("inline snapshot format must be csv or json")
    if kind == "csv":
        return {}, _nonempty_csv_rows(text), "csv"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("JSON input is invalid at line {}, column {}: {}"
                         .format(exc.lineno, exc.colno, exc.msg)) from exc
    metadata, rows = _rows_from_payload(payload)
    return metadata, rows, "json"


def _read_chain_snapshot_file(path):
    """Read a CSV or JSON snapshot from disk."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(path)
    size = source.stat().st_size
    if size > MAX_USER_DATA_BYTES:
        raise ValueError(
            "snapshot is {} bytes; the limit is {} bytes".format(
                size, MAX_USER_DATA_BYTES))
    suffix = source.suffix.lower()
    if suffix not in (".csv", ".json"):
        raise ValueError("snapshot file must end in .csv or .json")
    text = source.read_text(encoding="utf-8")
    return _read_chain_snapshot_text(text, suffix[1:])


def _read_chain_snapshot_input(args):
    """Read exactly one path, inline string, or structured JSON value."""
    path = getattr(args, "from_file", None)
    source_text = getattr(args, "source_text", None)
    source_data = getattr(args, "source_data", None)
    supplied = sum(value is not None for value in (path, source_text,
                                                    source_data))
    if supplied != 1:
        raise ValueError(
            "supply exactly one user snapshot input: a file path, "
            "source_text, or source_data")
    if path is not None:
        return _read_chain_snapshot_file(path)
    if source_text is not None:
        return _read_chain_snapshot_text(
            source_text, getattr(args, "source_format", None))
    encoded = json.dumps(source_data, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_USER_DATA_BYTES:
        raise ValueError(
            "structured snapshot is {} bytes; the limit is {} bytes".format(
                len(encoded), MAX_USER_DATA_BYTES))
    metadata, rows = _rows_from_payload(source_data)
    return metadata, rows, "json"


def _build_contract_from_row(row, underlying, requested_symbol, repairs=None,
                             row_number=None):
    """Normalize one uploaded contract row into snapshot schema fields."""
    repairs = repairs if repairs is not None else []
    prefix = "row {}: ".format(row_number) if row_number is not None else ""
    strike = _to_float(_first(row, "strike", "strike_price", "strikeprice"))
    if strike is None or strike <= 0:
        raise ValueError("invalid strike {!r}".format(_first(row, "strike")))

    raw_type = _first(row, "type", "call_put", "option_type", "right", "cp")
    option_type = _parse_option_type(raw_type)
    if str(raw_type).strip().lower() != option_type:
        repairs.append("{}normalized option type {!r} to {}".format(
            prefix, raw_type, option_type))

    bid = _to_float(_first(row, "bid", "bid_price"))
    ask = _to_float(_first(row, "ask", "ask_price"))
    mid = _to_float(_first(row, "mid", "mid_price"))
    last = _to_float(_first(row, "last", "last_price"))
    for name, value in (("bid", bid), ("ask", ask), ("mid", mid),
                        ("last", last)):
        if value is not None and value < 0:
            raise ValueError("{} cannot be negative".format(name))
    if mid is None:
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
            repairs.append("{}calculated mid from bid and ask".format(prefix))
        else:
            mid = None

    iv = _to_float(_first(row, "iv", "implied_volatility", "implied vol",
                          "implied-volatility", "sigma"))
    if iv is not None and IV_MAX <= iv <= 500.0:
        original = iv
        iv = iv / 100.0
        repairs.append(
            "{}converted implied volatility {} percent to {} per 1.00"
            .format(prefix, original, iv))
    if iv is not None and not (IV_MIN < iv < IV_MAX):
        raise ValueError(
            "implied volatility {!r} is outside ({}, {}) per 1.00".format(
                iv, IV_MIN, IV_MAX))

    volume = _to_int(_first(row, "volume", "vol", "trade_volume"))
    open_interest = _to_int(
        _first(row, "open_interest", "openinterest", "oi"))
    if volume is not None and volume < 0:
        raise ValueError("volume cannot be negative")
    if open_interest is not None and open_interest < 0:
        raise ValueError("open_interest cannot be negative")

    contract = {
        "symbol": _first(row, "symbol") or "{}{}{}".format(
            str(requested_symbol or underlying).upper(),
            option_type[0].upper(),
            str(int(strike) if float(strike).is_integer() else strike)),
        "type": option_type,
        "strike": float(strike),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "last": last,
        "volume": volume,
        "open_interest": open_interest,
    }
    if iv is not None:
        contract["iv"] = iv
        contract["iv_source"] = "provider"
        contract["iv_provider"] = iv
        contract["_provided_iv"] = True
    else:
        contract["iv"] = None
        contract["iv_source"] = None
        contract["iv_provider"] = None
        contract["_provided_iv"] = False

    if mid is not None:
        contract["mid_source"] = "quote"
    elif contract["last"] is not None:
        contract["mid_source"] = "last_trade"
    return contract


def add_arguments(parser):
    """Register the pull options: expiry, provider, risk free rate, dividend
    yield and output directory.
    """
    parser.add_argument("symbol", help="underlying ticker, for example SPY")
    parser.add_argument("--from-file", dest="from_file", default=None,
                        help="snapshot path (CSV or JSON) to build a chain "
                             "offline")
    parser.add_argument("--data-source", default=None,
                        help="name of the user-supplied data source")
    parser.add_argument("--accept-data-rights", action="store_true",
                        dest="rights_confirmed",
                        help="confirm that you can send this data for private "
                             "analysis")
    parser.add_argument("--expiry", default=None,
                        help="expiry as YYYY-MM-DD. Default: nearest listed")
    parser.add_argument("--provider", default=None,
                        help="force a provider instead of the registry order")
    parser.add_argument("--rate", type=float, default=None,
                        help="risk-free rate per 1.00. Default: fetched")
    parser.add_argument("--dividend-yield", type=float, default=None,
                        dest="dividend_yield",
                        help="continuous dividend yield per 1.00. Default: "
                             "fetched from trailing payments")
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


def _chain_from_user_data(args):
    """Build an option-chain map from a user-supplied snapshot."""
    metadata, rows, source_format = _read_chain_snapshot_input(args)
    if not rows:
        raise ValueError("uploaded snapshot has no contract rows")
    if len(rows) > MAX_USER_ROWS:
        raise ValueError("uploaded snapshot has {} rows; the limit is {}"
                         .format(len(rows), MAX_USER_ROWS))
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("each contract row must be a JSON object")

    first_row = rows[0] if rows else {}

    underlying = (str(args.symbol).upper() if args.symbol else
                  str(metadata.get("underlying") or _first(
                      first_row, "underlying", "symbol", "root", "ticker")
                  or "").upper())
    metadata_underlying = metadata.get("underlying") or metadata.get("ticker")
    if (args.symbol and metadata_underlying
            and str(metadata_underlying).upper() != underlying):
        raise ValueError("upload underlying {} does not match {}".format(
            metadata_underlying, underlying))
    requested_expiry = getattr(args, "expiry", None)
    expiry = (requested_expiry or metadata.get("expiry") or
              metadata.get("expiration") or _first(
                  first_row, "expiry", "expiration", "date"))
    if not expiry:
        raise ValueError("upload must include expiry (YYYY-MM-DD)")

    day_count = metadata.get("days_to_expiry")
    if day_count is not None:
        days_to_expiry = float(day_count)
    else:
        days_to_expiry = float(_days_to_expiry(expiry))
    if days_to_expiry < 0:
        raise ValueError("upload expiry {} has already passed".format(expiry))

    if not isinstance(underlying, str) or not underlying:
        raise ValueError("upload is missing underlying symbol")

    if (requested_expiry and metadata.get("expiry")
            and requested_expiry != metadata["expiry"]):
        raise ValueError("upload expiry {} does not match {}".format(
            requested_expiry, metadata["expiry"]))

    repairs = []
    problems = []
    contracts = []
    seen = set()
    crossed = 0
    for row_number, row in enumerate(rows, start=2 if source_format == "csv"
                                     else 1):
        row_underlying = _first(row, "underlying", "root", "ticker")
        row_expiry = _first(row, "expiry", "expiration", "date")
        try:
            if row_underlying and str(row_underlying).upper() != underlying:
                raise ValueError("underlying {!r} does not match {}".format(
                    row_underlying, underlying))
            if row_expiry and str(row_expiry) != str(expiry):
                raise ValueError("expiry {!r} does not match {}".format(
                    row_expiry, expiry))
            contract = _build_contract_from_row(
                row, underlying, underlying, repairs, row_number)
            key = (contract["type"], contract["strike"])
            if key in seen:
                raise ValueError("duplicate {} strike {}".format(*key))
            seen.add(key)
            if (contract.get("bid") is not None
                    and contract.get("ask") is not None
                    and contract["bid"] > contract["ask"]):
                crossed += 1
            contracts.append(contract)
        except (TypeError, ValueError) as exc:
            problems.append("row {}: {}".format(row_number, exc))

    if problems:
        shown = problems[:12]
        suffix = " (and {} more)".format(len(problems) - len(shown)) \
            if len(problems) > len(shown) else ""
        raise ValueError("snapshot needs correction: {}{}".format(
            "; ".join(shown), suffix))

    spot = _to_float(metadata.get("spot") or metadata.get("underlying_price")
                    or first_row.get("spot") or first_row.get("underlying_price"))
    if spot is None:
        raise ValueError("upload is missing spot")

    source_meta = metadata.get("meta") if isinstance(metadata.get("meta"), dict) \
        else {}
    data_source = (getattr(args, "data_source", None)
                   or metadata.get("data_source")
                   or metadata.get("source")
                   or metadata.get("provider")
                   or source_meta.get("provider_used"))
    if not data_source:
        raise ValueError(
            "user snapshot is missing its data source. Pass --data-source "
            "or include data_source in the JSON object")

    snapshot_timestamp = (
        metadata.get("spot_asof") or metadata.get("snapshot_timestamp")
        or metadata.get("timestamp") or metadata.get("asof")
        or source_meta.get("generated_utc")
        or _first(first_row, "spot_asof", "snapshot_timestamp", "timestamp",
                  "asof"))
    warnings = []
    if not snapshot_timestamp:
        warnings.append(
            "snapshot timestamp is missing; the data cannot be described as current")
    if crossed:
        warnings.append(
            "{} contract(s) have a bid above the ask; values were not swapped"
            .format(crossed))
    sides = {contract["type"] for contract in contracts}
    if sides != {"call", "put"}:
        warnings.append(
            "snapshot contains {} only".format(" and ".join(sorted(sides))))

    repair_count = len(repairs)
    if repair_count > 100:
        repairs = repairs[:100] + [
            "{} additional deterministic repairs are not listed".format(
                repair_count - 100)]

    return {
        "symbol": underlying,
        "expiry": expiry,
        "days_to_expiry": days_to_expiry,
        "actual_days_to_expiry": days_to_expiry,
        "expired": days_to_expiry < 0,
        "contracts": contracts,
        "listed_expiries": [expiry],
        "spot": spot,
        "spot_asof": snapshot_timestamp,
        "risk_free_rate": metadata.get("risk_free_rate"),
        "dividend_yield": metadata.get("dividend_yield"),
        "data_source": str(data_source),
        "normalization": {
            "source_format": source_format,
            "input_rows": len(rows),
            "output_contracts": len(contracts),
            "repair_count": repair_count,
            "repairs": repairs,
            "warnings": warnings,
        },
    }


def run(args):
    """Pull one option chain, solve implied volatility per contract where the
    price identifies it, and write a snapshot artifact.
    """
    if getattr(args, "from_file", None) is None:
        # MCP/agent calls use source_path; the CLI uses --from-file.
        args.from_file = getattr(args, "source_path", None)
    if not hasattr(args, "expiry"):
        args.expiry = None

    has_user_data = (args.from_file is not None
                     or getattr(args, "source_text", None) is not None
                     or getattr(args, "source_data", None) is not None)
    if has_user_data:
        if getattr(args, "rights_confirmed", False) is not True:
            raise ValueError(
                "user-supplied data needs an explicit rights confirmation. "
                "Confirm only if you can send the data for private analysis")
        chain = _chain_from_user_data(args)
        provider = SimpleNamespace(name="user snapshot")
        if chain["spot"] is None:
            raise ValueError("uploaded snapshot must include spot")
        quote = {"spot": chain["spot"],
                 "spot_asof": chain.get("spot_asof")}
        degraded = False
        reasons = []
        if chain["risk_free_rate"] is None:
            reasons.append(
                "risk-free rate missing from snapshot, will use default")
        if chain["dividend_yield"] is None:
            reasons.append("dividend yield missing from snapshot, set to zero")
        reasons.extend(chain["normalization"]["warnings"])
        if chain["normalization"]["warnings"]:
            degraded = True
    else:
        provider, choice = resolve(CAP_OPTION_CHAIN, args.provider)
        quote = provider.underlying_quote(args.symbol)
        chain = provider.option_chain(args.symbol, args.expiry)
        degraded = choice["degraded"]
        reasons = list(choice["skipped"])

    if args.rate is not None:
        rate, rate_source = float(args.rate), "user"
    else:
        if has_user_data and chain.get("risk_free_rate") is not None:
            rate, rate_source = float(chain["risk_free_rate"]), "user_file"
        elif has_user_data:
            rate, rate_source = 0.04, "default"
            degraded = True
            reasons.append("risk-free rate missing; defaulted to 0.04")
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

    # A zero dividend yield is not a safe default, it is a wrong one for
    # anything that pays. Measured on a 173 day TLT chain against its real
    # 4.7 percent yield: at-the-money implied volatility came out 0.0737
    # instead of 0.1133, understated by 54 percent, and delta 0.635 instead
    # of 0.491. Every Greek and every probability built on that inherits it.
    if args.dividend_yield is not None:
        q, q_source, q_note = float(args.dividend_yield), "user", None
    elif has_user_data and chain.get("dividend_yield") is not None:
        q, q_source, q_note = float(chain["dividend_yield"]), "user_file", None
    else:
        q, q_source, q_note = 0.0, None, None
        try:
            if has_user_data:
                raise ValueError("file snapshot has no dividend yield")
            yield_provider, _ = resolve(CAP_DIVIDEND_YIELD, args.provider)
            fetched_q = yield_provider.dividend_yield(args.symbol, spot=spot)
        except Exception as exc:
            if not has_user_data:
                fetched_q = {"dividend_yield": None,
                             "note": "{}: {}".format(type(exc).__name__, exc)}
            else:
                fetched_q = {"dividend_yield": None,
                             "note": "uploaded snapshot had no yield and no "
                                     "override was passed"}
        if fetched_q.get("dividend_yield") is None:
            degraded = True
            q_note = fetched_q.get("note") or "no dividend yield available"
            reasons.append(
                "dividend yield assumed zero: {}. Pass --dividend-yield to "
                "price against the real one".format(q_note))
        else:
            q = float(fetched_q["dividend_yield"])
            q_source = fetched_q.get("source")
            q_note = fetched_q.get("note")

    t = chain["days_to_expiry"] / 365.0

    with_iv = 0
    from_provider = 0
    from_last_trade = 0
    for contract in chain["contracts"]:
        provided_iv = has_user_data and contract.pop("_provided_iv", False)
        if provided_iv:
            iv, source = contract["iv"], contract.get("iv_source")
            # Snapshot-provided volatility is explicit input, not a fallback
            # from a live provider capability.
        else:
            iv, source = _solve_iv(engine, contract, spot, t, rate, q)
            contract["iv"] = iv
            contract["iv_source"] = source
        if iv is not None:
            with_iv += 1
        if source == "provider" and not provided_iv:
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
    if has_user_data:
        notes.extend(chain["normalization"]["repairs"])

    payload = {
        "meta": envelope(
            schema=CHAIN_SNAPSHOT,
            tool="optiondesk chain",
            provider_used=provider.name,
            degraded=degraded,
            degraded_reason="; ".join(reasons) or None,
            inputs={"symbol": args.symbol, "expiry": args.expiry,
                    "rate_source": rate_source,
                    "dividend_yield": q,
                    "user_supplied": has_user_data,
                    "data_source": chain.get("data_source"),
                    "rights_asserted": bool(has_user_data)},
            engine_version=engine_bridge.status()["version"],
            notes=notes,
        ),
        "underlying": args.symbol,
        "spot": spot,
        "spot_asof": quote.get("spot_asof"),
        "risk_free_rate": rate,
        "dividend_yield": q,
        "dividend_yield_source": q_source,
        "dividend_yield_note": q_note,
        "expiry": chain["expiry"],
        "days_to_expiry": chain["days_to_expiry"],
        "contracts": chain["contracts"],
        "data_source": chain.get("data_source"),
        "data_rights": ({
            "asserted_by_user": True,
            "use": "private analysis",
            "public_display": False,
        } if has_user_data else None),
        "normalization": chain.get("normalization"),
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
        "data_source": chain.get("data_source"),
        "normalization": chain.get("normalization"),
        "dividend_yield": q,
        "dividend_yield_source": q_source,
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
