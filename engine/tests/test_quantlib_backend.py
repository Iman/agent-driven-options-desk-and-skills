import pytest
from optiondesk_engine.pricing.quantlib_backend import validate_request, calculate


def request():
    return dict(spot=80, strike=100, valuation_date="2026-09-12", expiry="2027-09-12",
                volatility=.2, rate=.05, dividend_yield=0, kind="put", exercise_style="american")


def test_american_put_exercises_and_european_matches_reference():
    pytest.importorskip("QuantLib")
    result = calculate(request())
    assert result["price"] == pytest.approx(20, abs=.001)
    assert result["european_reference"] == pytest.approx(16.982362022883578, abs=1e-9)
    assert result["units"] == "premium per underlying unit"


@pytest.mark.parametrize("change", [{"volatility":None},{"volatility":float("nan")},
    {"spot":0},{"exercise_style":"bermudan"},{"expiry":"2026-09-12"},{"kind":"stock"}])
def test_missing_or_unsupported_terms_are_refused(change):
    value=request();value.update(change)
    with pytest.raises(ValueError): validate_request(value)
