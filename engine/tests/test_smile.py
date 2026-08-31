"""Volatility smile geometry.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
"""

import pytest

from optiondesk_engine.analytics.smile import smile_metrics


def _rows(skew=0.0, base_iv=0.20):
    """Ladder rows with a linear skew: lower strikes carry more volatility."""
    rows = []
    for strike in range(80, 121, 5):
        moneyness = strike / 100.0 - 1.0
        iv = base_iv - skew * moneyness
        # Deltas that behave like real ones: calls fall from 1 to 0 across
        # the strikes, puts are their mirror.
        call_delta = max(0.01, min(0.99, 0.5 - moneyness * 3.0))
        rows.append({"type": "call", "strike": float(strike), "iv": iv,
                     "delta": call_delta})
        rows.append({"type": "put", "strike": float(strike), "iv": iv,
                     "delta": call_delta - 1.0})
    return rows


def test_atm_is_the_nearest_listed_strike():
    metrics = smile_metrics(_rows(), spot=101.0, days=30)
    assert metrics["atm_strike"] == 100.0
    assert metrics["atm_iv"] == pytest.approx(0.20)


def test_downside_skew_gives_a_positive_risk_reversal():
    # Lower strikes richer means the downside is bid, which the convention
    # reports as a positive risk reversal.
    metrics = smile_metrics(_rows(skew=0.4), spot=100.0, days=30)
    assert metrics["risk_reversal"] > 0
    assert metrics["put_wing"]["strike"] < metrics["call_wing"]["strike"]
    assert metrics["skew_slope_per_percent"] < 0


def test_a_flat_smile_has_no_skew_and_no_convexity():
    metrics = smile_metrics(_rows(skew=0.0), spot=100.0, days=30)
    assert metrics["risk_reversal"] == pytest.approx(0.0)
    assert metrics["butterfly"] == pytest.approx(0.0)
    assert metrics["skew_slope_per_percent"] == pytest.approx(0.0, abs=1e-12)


def test_expected_move_scales_with_the_square_root_of_time():
    thirty = smile_metrics(_rows(), spot=100.0, days=30)["expected_move"]
    onetwenty = smile_metrics(_rows(), spot=100.0, days=120)["expected_move"]
    assert onetwenty / thirty == pytest.approx(2.0, rel=1e-9)


def test_missing_wings_report_none_rather_than_extrapolating():
    # A chain with only deep in the money calls never reaches 25 delta on
    # the upside, so there is no risk reversal to quote.
    rows = [{"type": "call", "strike": 80.0, "iv": 0.3, "delta": 0.95},
            {"type": "call", "strike": 85.0, "iv": 0.29, "delta": 0.92}]
    metrics = smile_metrics(rows, spot=100.0, days=30)
    assert metrics["risk_reversal"] is None
    assert metrics["butterfly"] is None
    assert metrics["atm_iv"] == pytest.approx(0.29)


def test_no_graded_contracts_returns_none():
    assert smile_metrics([], spot=100.0, days=30) is None
    assert smile_metrics([{"type": "call", "strike": 100.0, "iv": None}],
                         spot=100.0, days=30) is None


def test_days_absent_means_no_expected_move():
    metrics = smile_metrics(_rows(), spot=100.0, days=None)
    assert metrics["expected_move"] is None
    assert metrics["expected_range"] is None
    assert metrics["atm_iv"] is not None


def test_convention_is_carried_with_the_numbers():
    metrics = smile_metrics(_rows(), spot=100.0, days=30)
    assert "put volatility minus" in metrics["convention"]
