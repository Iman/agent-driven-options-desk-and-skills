"""Dealer gamma exposure, walls, flip level and max pain.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.
"""

import pytest

from optiondesk_engine.analytics.exposure import chain_exposure, max_pain


def _contracts(spec):
    """spec: list of (type, strike, gamma, open_interest, volume)."""
    return [{"type": kind, "strike": strike, "gamma": gamma,
             "open_interest": oi, "volume": volume}
            for kind, strike, gamma, oi, volume in spec]


def test_call_exposure_is_positive_and_put_negative():
    contracts = _contracts([
        ("call", 100.0, 0.02, 1000, 50),
        ("put", 100.0, 0.02, 1000, 50),
    ])
    result = chain_exposure(contracts, spot=100.0)
    row = result["rows"][0]
    assert row["call_gex"] > 0
    assert row["put_gex"] < 0
    # Equal gamma and open interest on both sides cancel exactly.
    assert row["net_gex"] == pytest.approx(0.0)


def test_exposure_scales_as_documented():
    # gamma * open interest * multiplier * spot^2 * 0.01
    contracts = _contracts([("call", 100.0, 0.02, 1000, 0)])
    result = chain_exposure(contracts, spot=100.0)
    expected = 0.02 * 1000 * 100.0 * 100.0 * 100.0 * 0.01
    assert result["rows"][0]["call_gex"] == pytest.approx(expected)
    assert result["net_gex"] == pytest.approx(expected)


def test_walls_and_flip_level():
    contracts = _contracts([
        ("put", 90.0, 0.03, 5000, 10),
        ("put", 95.0, 0.02, 1000, 10),
        ("call", 105.0, 0.02, 1000, 10),
        ("call", 110.0, 0.04, 6000, 10),
    ])
    result = chain_exposure(contracts, spot=100.0)
    assert result["put_wall"]["strike"] == 90.0
    assert result["call_wall"]["strike"] == 110.0
    # Cumulative exposure starts negative at the puts and turns positive
    # through the calls, so the crossing sits between them.
    assert result["gamma_flip"] is not None
    assert 95.0 < result["gamma_flip"] <= 110.0
    assert result["regime"] in ("dampening", "amplifying")


def test_flip_is_none_when_the_profile_never_crosses():
    contracts = _contracts([("call", 105.0, 0.02, 1000, 0),
                            ("call", 110.0, 0.02, 1000, 0)])
    result = chain_exposure(contracts, spot=100.0)
    assert result["gamma_flip"] is None
    assert result["net_gex"] > 0
    assert result["regime"] == "dampening"


def test_missing_open_interest_is_skipped_not_zeroed():
    contracts = [
        {"type": "call", "strike": 100.0, "gamma": 0.02,
         "open_interest": None, "volume": 5},
        {"type": "call", "strike": 105.0, "gamma": 0.02,
         "open_interest": 1000, "volume": 5},
    ]
    result = chain_exposure(contracts, spot=100.0)
    assert result["skipped"] == 1
    assert [r["strike"] for r in result["rows"]] == [105.0]


def test_put_call_ratios():
    contracts = _contracts([
        ("call", 100.0, 0.02, 1000, 200),
        ("put", 100.0, 0.02, 2000, 600),
    ])
    result = chain_exposure(contracts, spot=100.0)
    assert result["put_call_oi_ratio"] == pytest.approx(2.0)
    assert result["put_call_volume_ratio"] == pytest.approx(3.0)


def test_exposure_states_its_assumption():
    result = chain_exposure(_contracts([("call", 100.0, 0.02, 10, 1)]),
                            spot=100.0)
    assert "dealers are long calls and short puts" in result["assumption"]


def test_spot_must_be_positive():
    with pytest.raises(ValueError):
        chain_exposure(_contracts([("call", 100.0, 0.02, 10, 1)]), spot=0)


def test_max_pain_is_where_payout_is_smallest():
    # All open interest in the 100 calls: settling at or below 100 pays
    # nothing, and the lowest listed strike is chosen.
    contracts = _contracts([
        ("call", 100.0, 0.02, 1000, 0),
        ("call", 110.0, 0.02, 0, 0),
        ("put", 90.0, 0.02, 0, 0),
    ])
    result = max_pain(contracts)
    assert result["strike"] == 90.0
    assert result["payout_at_strike"] == pytest.approx(0.0)
    assert len(result["profile"]) == 3


def test_max_pain_balances_two_sided_open_interest():
    contracts = _contracts([
        ("call", 90.0, 0.02, 1000, 0),
        ("call", 100.0, 0.02, 1000, 0),
        ("put", 100.0, 0.02, 1000, 0),
        ("put", 110.0, 0.02, 1000, 0),
    ])
    result = max_pain(contracts)
    assert result["strike"] == 100.0


def test_max_pain_returns_none_without_open_interest():
    assert max_pain([{"type": "call", "strike": 100.0}]) is None
