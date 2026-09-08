"""Acceptance steps use production commands and authored sample data."""
import json
from pathlib import Path

import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from optiondesk.cli.__main__ import build_parser, HANDLERS

scenarios('sample_desk.feature')
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def journey(tmp_path, monkeypatch):
    monkeypatch.setenv('PUBLIC_DATA_MODE', 'demo')
    return {'directory': tmp_path, 'input': tmp_path / 'input.json', 'results': {}}


def command(journey, *argv):
    args = build_parser().parse_args([*argv, '--out-dir', str(journey['directory'])])
    return HANDLERS[args.command](args)


@given('a synthetic chain and an empty desk')
def sample(journey):
    journey['input'].write_bytes((ROOT / 'examples/chain-synth.json').read_bytes())


@given('I import the chain with data rights confirmed')
@when('I import the chain with data rights confirmed')
def import_chain(journey):
    journey['chain'] = command(journey, 'chain', 'SYNTH', '--from-file',
                               str(journey['input']), '--accept-data-rights')
    journey['saved'] = next(journey['directory'].glob('chain_*.json'))
    journey['before'] = journey['saved'].read_bytes()
    journey['chain'] = json.loads(journey['before'])


@when('I calculate Greeks, positioning, and structure comparisons')
def research(journey):
    for name in ['greeks', 'exposure', 'compare']:
        command(journey, name)
        prefix = 'comparison' if name == 'compare' else name
        path = next(journey['directory'].glob(prefix + '_*.json'))
        journey['results'][name] = json.loads(path.read_text())


@then('the desk contains usable research results with source notes')
def usable(journey):
    assert journey['results']['greeks']['rows']
    assert journey['results']['compare']['rankable_count'] > 0
    assert len(list(journey['directory'].glob('exposure_*.json'))) == 1
    assert journey['chain']['data_source']
    assert journey['chain']['meta']['schema']
    assert 'synthetic' in json.dumps(journey['chain']).lower()


@when(parsers.parse('I import with {problem}'))
def rejected_import(journey, problem):
    payload = json.loads(journey['input'].read_text())
    argv = ['chain', 'SYNTH', '--from-file', str(journey['input'])]
    if problem != 'unconfirmed rights':
        argv.append('--accept-data-rights')
    if problem == 'missing spot':
        payload.pop('spot')
    if problem == 'missing source':
        payload.pop('data_source', None)
    journey['input'].write_text(json.dumps(payload))
    with pytest.raises((ValueError, PermissionError)) as caught:
        command(journey, *argv)
    journey['error'] = str(caught.value)


@then('the import is refused and no chain is written')
def no_chain(journey):
    assert journey['error']
    assert not list(journey['directory'].glob('chain_*.json'))


@when('I try to replace it with malformed JSON')
def malformed(journey):
    journey['input'].write_text('{invalid')
    with pytest.raises(ValueError):
        command(journey, 'chain', 'SYNTH', '--from-file', str(journey['input']),
                '--accept-data-rights')


@then('the import is refused and the saved chain is unchanged')
def preserved(journey):
    assert journey['saved'].read_bytes() == journey['before']


@given('one contract has neither prices nor implied volatility')
def unpriced(journey):
    payload = json.loads(journey['input'].read_text())
    contract = payload['contracts'][0]
    for key in ['bid', 'ask', 'mid', 'last', 'iv', 'iv_provider']:
        contract.pop(key, None)
    journey['input'].write_text(json.dumps(payload))
    journey['contract_count'] = len(payload['contracts'])


@when('I calculate the full Greek ladder')
def ladder(journey):
    command(journey, 'greeks', '--band', '1')
    path = next(journey['directory'].glob('greeks_*.json'))
    journey['ladder'] = json.loads(path.read_text())


@then('the unpriced contract is counted as skipped without invented volatility')
def skipped(journey):
    assert journey['chain']['counts']['without_iv'] == 1
    assert len(journey['ladder']['rows']) == journey['contract_count'] - 1
    assert journey['ladder']['skipped']
