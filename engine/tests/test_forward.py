"""Forward-test marking.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.

The property that matters most here is the refusal: a position with a leg
that has no later quote must not be marked. Treating a missing leg as
worthless reports a profit that does not exist, and it does so most often
on exactly the positions where a wing has gone illiquid.
"""

import pytest

from optiondesk_engine.backtest.forward import mark_position, settle_position
from optiondesk_engine.strategies.payoff import Leg, pnl_at_expiry


def _position(entry_spot=100.0):
    return {
        "entry_spot": entry_spot,
        "legs": [
            {"kind": "call", "side": "short", "strike": 105.0, "qty": 1.0,
             "price": 2.00, "symbol": "TESTC105"},
            {"kind": "call", "side": "long", "strike": 110.0, "qty": 1.0,
             "price": 0.80, "symbol": "TESTC110"},
        ],
    }


def _snapshot(spot=100.0, marks=None, **kwargs):
    marks = marks or {"TESTC105": 1.20, "TESTC110": 0.40}
    contracts = []
    for symbol, mid in marks.items():
        strike = float(symbol.replace("TESTC", ""))
        contracts.append(dict({
            "symbol": symbol, "type": "call", "strike": strike,
            "bid": mid - 0.05, "ask": mid + 0.05, "mid": mid,
        }, **kwargs))
    return {"spot": spot, "contracts": contracts,
            "meta": {"generated_utc": "2026-09-01T20:00:00+00:00"}}


def test_a_credit_spread_that_decayed_shows_a_profit():
    # Sold at 2.00 and bought at 0.80 for a 1.20 credit; now worth 0.80.
    # A short position gains as the value it owes falls.
    result = mark_position(_position(), _snapshot())
    assert result["markable"] is True
    assert result["entry_value"] == pytest.approx(-1.20)
    assert result["mark_value"] == pytest.approx(-0.80)
    assert result["profit"] == pytest.approx(0.40)


def test_a_missing_leg_stops_the_mark_rather_than_counting_as_zero():
    """The refusal this module exists for.

    A wing that has gone illiquid and dropped out of the chain would, if
    marked at zero, turn a short spread into a full-credit profit. That is
    the most flattering possible lie and it appears exactly when the
    position is in trouble.
    """
    snapshot = _snapshot(marks={"TESTC105": 1.20})
    result = mark_position(_position(), snapshot)
    assert result["markable"] is False
    assert any("no later quote" in problem for problem in result["problems"])
    assert "profit" not in result
    assert "treating it as zero" in result["note"]


def test_legs_match_by_strike_when_the_symbol_has_changed():
    snapshot = _snapshot()
    for contract in snapshot["contracts"]:
        contract["symbol"] = "RENAMED" + str(int(contract["strike"]))
    result = mark_position(_position(), snapshot)
    assert result["markable"] is True
    assert all(leg["matched_by"] == "strike" for leg in result["legs"])


def test_a_mark_from_a_last_trade_is_flagged():
    snapshot = _snapshot()
    for contract in snapshot["contracts"]:
        contract["mid_source"] = "last_trade"
    result = mark_position(_position(), snapshot)
    assert result["stale_marks"] == 2
    assert any("last trade" in note for note in result["notes"])


def test_a_contract_with_no_usable_mark_is_a_problem_not_a_zero():
    snapshot = _snapshot()
    for contract in snapshot["contracts"]:
        contract.update({"mid": None, "bid": None, "ask": None})
    result = mark_position(_position(), snapshot)
    assert result["markable"] is False
    assert len(result["problems"]) == 2


def test_the_underlying_leg_marks_at_spot():
    position = {
        "entry_spot": 100.0,
        "legs": [
            {"kind": "underlying", "side": "long", "strike": None,
             "qty": 1.0, "price": 100.0, "symbol": None},
            {"kind": "call", "side": "short", "strike": 105.0, "qty": 1.0,
             "price": 2.0, "symbol": "TESTC105"},
        ],
    }
    result = mark_position(position, _snapshot(spot=103.0,
                                               marks={"TESTC105": 1.5}))
    assert result["markable"] is True
    # Stock up three. The short call was sold at 2.00 and is now worth
    # 1.50, so it has gained half a point as well: 3.50 in total.
    assert result["profit"] == pytest.approx(3.50)
    assert result["underlying_move"] == pytest.approx(0.03)


def test_settlement_uses_the_payoff_engine():
    def build(legs):
        return [Leg(l["kind"], 1 if l["side"] == "long" else -1,
                    float(l["price"]), strike=l["strike"],
                    qty=float(l["qty"])) for l in legs]

    result = settle_position(_position(), 100.0, pnl_at_expiry, build)
    # Both calls expire worthless, so the credit is kept in full.
    assert result["profit"] == pytest.approx(1.20)
    assert result["underlying_move"] == pytest.approx(0.0)
    assert "assumes the entry was achieved" in result["note"]


def test_settlement_through_the_short_strike_costs_the_width():
    def build(legs):
        return [Leg(l["kind"], 1 if l["side"] == "long" else -1,
                    float(l["price"]), strike=l["strike"],
                    qty=float(l["qty"])) for l in legs]

    result = settle_position(_position(), 120.0, pnl_at_expiry, build)
    # Five wide, 1.20 credit: the loss is the width less the credit.
    assert result["profit"] == pytest.approx(-3.80)
