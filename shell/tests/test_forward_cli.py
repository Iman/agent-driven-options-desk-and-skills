"""Paper-ledger commands with local files and no external data provider."""
import argparse
import json

import pytest

from optiondesk.cli import forward


def run(directory, *argv):
    parser = forward.add_arguments(argparse.ArgumentParser())
    return forward.run(parser.parse_args([*argv, '--out-dir', str(directory)]))


@pytest.fixture
def plan(tmp_path):
    payload = {
        'strategy': 'bear_call_spread', 'underlying': 'TEST', 'expiry': '2026-09-18',
        'spot': 100, 'size': 1, 'trade_type': 'credit',
        'legs': [
            {'kind': 'call', 'side': 'short', 'strike': 105, 'qty': 1,
             'price': 2, 'symbol': 'TESTC105'},
            {'kind': 'call', 'side': 'long', 'strike': 110, 'qty': 1,
             'price': .8, 'symbol': 'TESTC110'},
        ],
    }
    path = tmp_path / 'strategy_TEST_bear_call_spread_2026-09-18.json'
    path.write_text(json.dumps(payload))
    return path


def test_open_records_signed_entry_and_thesis(tmp_path, plan):
    result = run(tmp_path, 'open', '--plan', str(plan), '--thesis', 'Synthetic test')
    assert result['entry_value'] == pytest.approx(-1.2)
    ledger = json.loads((tmp_path / forward.LEDGER).read_text())
    assert ledger['summary']['open'] == 1
    assert ledger['positions'][0]['id'] == result['id']
    assert ledger['positions'][0]['thesis'] == 'Synthetic test'


def test_open_without_a_plan_refuses_to_write(tmp_path):
    with pytest.raises(FileNotFoundError, match='no strategy plan'):
        run(tmp_path, 'open')
    assert not (tmp_path / forward.LEDGER).exists()


def test_open_can_select_a_saved_strategy(tmp_path, plan):
    result = run(tmp_path, 'open', '--strategy', 'bear_call_spread', '--underlying', 'TEST')
    assert result['strategy'] == 'bear_call_spread'


@pytest.mark.parametrize('price,profit', [(100, 1.2), (120, -3.8)])
def test_close_records_profit_or_loss_once(tmp_path, plan, price, profit):
    opened = run(tmp_path, 'open', '--plan', str(plan))
    run(tmp_path, 'close', '--id', opened['id'], '--price', str(price))
    status = run(tmp_path, 'status')
    assert (status['open'], status['closed']) == (0, 1)
    assert status['settled_profit'] == pytest.approx(profit)
    before = (tmp_path / forward.LEDGER).read_bytes()
    with pytest.raises(ValueError):
        run(tmp_path, 'close', '--id', opened['id'], '--price', str(price))
    assert (tmp_path / forward.LEDGER).read_bytes() == before


@pytest.mark.parametrize('argv', [('close',), ('close', '--id', 'missing', '--price', '100')])
def test_invalid_close_keeps_the_open_position(tmp_path, plan, argv):
    run(tmp_path, 'open', '--plan', str(plan))
    before = (tmp_path / forward.LEDGER).read_bytes()
    with pytest.raises(ValueError):
        run(tmp_path, *argv)
    assert (tmp_path / forward.LEDGER).read_bytes() == before


def test_close_without_price_or_chain_is_a_refusal(tmp_path, plan):
    opened = run(tmp_path, 'open', '--plan', str(plan))
    with pytest.raises(ValueError, match='price'):
        run(tmp_path, 'close', '--id', opened['id'])
    assert run(tmp_path, 'status')['open'] == 1


def test_mark_without_a_chain_does_not_invent_profit(tmp_path, plan):
    run(tmp_path, 'open', '--plan', str(plan))
    result = run(tmp_path, 'mark')
    assert not result['marked']
    assert len(result['unmarkable']) == 1
    status = run(tmp_path, 'status')['positions'][0]
    assert status['marks'] == 0
    assert status['last_mark_profit'] is None


def test_mark_uses_matching_quotes_and_filters_other_symbols(tmp_path, plan, chain_snapshot):
    run(tmp_path, 'open', '--plan', str(plan))
    snapshot = chain_snapshot()
    (tmp_path / 'chain_TEST_2026-09-18.json').write_text(json.dumps(snapshot))
    assert len(run(tmp_path, 'mark')['marked']) == 1
    status = run(tmp_path, 'status')['positions'][0]
    assert status['marks'] == 1
    assert status['last_mark_profit'] is not None
    assert not run(tmp_path, 'status', '--underlying', 'OTHER')['positions']
    assert not run(tmp_path, 'mark', '--underlying', 'OTHER')['marked']


def test_mark_with_a_missing_leg_reports_no_profit(tmp_path, plan, chain_snapshot):
    run(tmp_path, 'open', '--plan', str(plan))
    snapshot = chain_snapshot(strikes=(105,))
    (tmp_path / 'chain_TEST_2026-09-18.json').write_text(json.dumps(snapshot))
    result = run(tmp_path, 'mark')
    assert not result['marked']
    assert len(result['unmarkable']) == 1
    assert run(tmp_path, 'status')['positions'][0]['last_mark_profit'] is None
