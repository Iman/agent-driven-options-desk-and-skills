"""Adapter success and failure responses, with the HTTP boundary replaced."""
import io
import json
import math
import urllib.error
from datetime import date, timedelta

import pytest

from optiondesk.providers import alphavantage as module
from optiondesk.providers.base import ProviderDataError, ProviderUnavailable


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr(module, 'provider_key', lambda _: 'fictional-test-token')
    return module.AlphaVantageProvider()


def respond(monkeypatch, payload):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(body))


def history(count=100):
    return {'Time Series (Daily)': {
        str(date(2026, 1, 1) + timedelta(days=i)): {'4. close': str(100 + i)}
        for i in reversed(range(count))}}


def test_history_sorts_dates_and_discloses_plan_limit(adapter, monkeypatch):
    respond(monkeypatch, history())
    result = adapter.underlying_history('TEST')
    assert result['dates'] == sorted(result['dates'])
    assert len(result['returns']) == 99
    assert result['returns'][0] == pytest.approx(math.log(101 / 100))
    assert result['truncated_by_plan'] is True
    assert result['requested_observations'] == 504
    assert result['limitation']


def test_history_can_satisfy_a_shorter_requested_window(adapter, monkeypatch):
    respond(monkeypatch, history())
    result = adapter.underlying_history('TEST', period='0.25y')
    assert len(result['closes']) == 63
    assert result['truncated_by_plan'] is False
    assert result['limitation'] is None


def test_history_counts_unusable_return_pairs(adapter, monkeypatch):
    payload = history()
    payload['Time Series (Daily)']['2026-01-02']['4. close'] = '0'
    respond(monkeypatch, payload)
    result = adapter.underlying_history('TEST')
    assert result['spliced_gaps'] == 2
    assert len(result['returns']) == 97
    assert all(math.isfinite(value) for value in result['returns'])


@pytest.mark.parametrize('payload', [{}, history(59)])
def test_missing_or_short_history_is_refused(adapter, monkeypatch, payload):
    respond(monkeypatch, payload)
    with pytest.raises(ProviderDataError):
        adapter.underlying_history('TEST')


def test_quote_preserves_price_and_date(adapter, monkeypatch):
    respond(monkeypatch, {'Global Quote': {'05. price': '101.5',
                                         '07. latest trading day': '2026-09-08'}})
    result = adapter.underlying_quote('TEST')
    assert result['spot'] == 101.5
    assert result['spot_asof'] == '2026-09-08'


def test_missing_quote_is_refused(adapter, monkeypatch):
    respond(monkeypatch, {})
    with pytest.raises(ProviderDataError, match='no quote'):
        adapter.underlying_quote('TEST')


@pytest.mark.parametrize('field', ['Note', 'Information', 'Error Message'])
def test_api_error_in_a_successful_http_response_is_refused(adapter, monkeypatch, field):
    respond(monkeypatch, {field: 'Request limit reached'})
    with pytest.raises(ProviderDataError, match='Request limit reached'):
        adapter.underlying_quote('TEST')


def test_invalid_json_is_refused(adapter, monkeypatch):
    respond(monkeypatch, b'<html>unavailable</html>')
    with pytest.raises(ProviderDataError, match='not JSON'):
        adapter.underlying_quote('TEST')


@pytest.mark.parametrize('error', [
    urllib.error.HTTPError('https://example.invalid/?apikey=fictional-test-token', 429, 'limit', {}, None),
    urllib.error.URLError('fictional-test-token'), TimeoutError('fictional-test-token'),
])
def test_transport_errors_do_not_expose_the_key(adapter, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(module.urllib.request, 'urlopen', fail)
    with pytest.raises(ProviderDataError) as caught:
        adapter.underlying_quote('TEST')
    assert 'fictional-test-token' not in str(caught.value)


def test_missing_key_stops_before_http(adapter, monkeypatch):
    monkeypatch.setattr(module, 'provider_key', lambda _: None)
    with pytest.raises(ProviderUnavailable, match='no Alpha Vantage key'):
        adapter.underlying_quote('TEST')
