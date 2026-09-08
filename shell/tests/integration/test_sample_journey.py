"""Real CLI, MCP stdio, HTTP, and browser checks using synthetic inputs."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def environment(tmp_path):
    # Child processes inherit selected environment variables and cannot fetch provider data.
    env = {key: value for key, value in os.environ.items()
           if key in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TMPDIR', 'TEMP', 'TMP',
                      'PLAYWRIGHT_BROWSERS_PATH'}}
    env.update(PUBLIC_DATA_MODE='demo', NO_COLOR='1', PYTHONIOENCODING='utf-8',
               OPTIONDESK_ARTIFACTS=str(tmp_path))
    return env


def cli(directory, env, *args, success=True):
    result = subprocess.run([sys.executable, '-m', 'optiondesk.cli', *args,
                             '--out-dir', str(directory)], cwd=directory, env=env,
                            capture_output=True, text=True, timeout=60)
    assert (result.returncode == 0) == success, result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def populated(tmp_path, environment):
    near = tmp_path / 'chain_SYNTH_2026-10-08.json'
    far = tmp_path / 'chain_SYNTH_2026-11-07.json'
    for filename in ['chain-synth.json', 'chain-synth-far.json']:
        cli(tmp_path, environment, 'chain', 'SYNTH', '--from-file',
            str(ROOT / 'examples' / filename), '--accept-data-rights')
    for command in ['greeks', 'exposure', 'compare']:
        cli(tmp_path, environment, command, '--snapshot', str(near))
    cli(tmp_path, environment, 'strategy', 'calendar_spread',
        '--snapshot', str(near), '--far-snapshot', str(far))
    cli(tmp_path, environment, 'plots', 'SYNTH', '--snapshot', str(near))
    return tmp_path


def test_cli_import_to_research_and_paper_settlement(populated, environment):
    directory = populated
    comparison = json.loads((directory / 'comparison_SYNTH_2026-10-08.json').read_text())
    assert comparison['rankable_count'] > 0
    calendar = json.loads((directory / 'strategy_SYNTH_calendar_spread_2026-10-08.json').read_text())
    assert len({leg['days_to_expiry'] for leg in calendar['legs']}) == 2
    pngs = list(directory.glob('*.png'))
    assert pngs and all(p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for p in pngs)
    plan = directory / 'strategy_SYNTH_iron_condor_2026-10-08.json'
    opened = cli(directory, environment, 'forward', 'open', '--plan', str(plan))
    marked = cli(directory, environment, 'forward', 'mark')
    assert len(marked['marked']) == 1
    cli(directory, environment, 'forward', 'close', '--id', opened['id'], '--price', '100')
    status = cli(directory, environment, 'forward', 'status')
    assert (status['open'], status['closed']) == (0, 1)
    before = (directory / 'forward_ledger.json').read_bytes()
    refused = cli(directory, environment, 'forward', 'close', '--id', opened['id'],
                  '--price', '100', success=False)
    assert refused['error'] == 'ValueError'
    assert (directory / 'forward_ledger.json').read_bytes() == before


def test_cli_rejected_input_preserves_the_previous_chain(populated, environment):
    path = populated / 'chain_SYNTH_2026-10-08.json'
    before = path.read_bytes()
    invalid = populated / 'broken.json'
    invalid.write_text('{invalid')
    failure = cli(populated, environment, 'chain', 'SYNTH', '--from-file', str(invalid),
                  '--accept-data-rights', success=False)
    assert failure['error']
    assert path.read_bytes() == before
    refused = cli(populated, environment, 'chain', 'SYNTH', success=False)
    assert 'demo' in refused['message'].lower()
    assert path.read_bytes() == before


def test_mcp_stdio_survives_bad_requests_then_calculates(tmp_path, environment):
    messages = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
         'params': {'name': 'option_chain_snapshot', 'arguments': {
             'symbol': 'SYNTH', 'source_path': str(ROOT / 'examples/chain-synth.json'),
             'rights_confirmed': True, 'out_dir': str(tmp_path)}}},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
         'params': {'name': 'option_greeks_ladder', 'arguments': {
             'snapshot': str(tmp_path / 'missing.json'), 'out_dir': str(tmp_path)}}},
        {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
         'params': {'name': 'option_greeks_ladder', 'arguments': {
             'snapshot': str(tmp_path / 'chain_SYNTH_2026-10-08.json'),
             'out_dir': str(tmp_path)}}},
    ]
    wire = '{invalid\n' + '\n'.join(json.dumps(m) for m in messages) + '\n'
    result = subprocess.run([sys.executable, '-m', 'optiondesk.mcp.server'],
                            input=wire, cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == 5
    assert responses[0]['error']['code'] == -32700
    by_id = {r['id']: r for r in responses if r.get('id') is not None}
    assert not by_id[2]['result'].get('isError'), by_id[2]
    assert by_id[3]['result']['isError'] is True
    assert not by_id[4]['result'].get('isError'), by_id[4]
    assert list(tmp_path.glob('greeks_SYNTH_*.json'))


@pytest.fixture
def dashboard(populated, environment):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([sys.executable, '-m', 'optiondesk.cli', 'dashboard',
                                '--host', '127.0.0.1', '--port', str(port),
                                '--out-dir', str(populated)], cwd=populated,
                               env=environment, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, text=True)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail('Dashboard exited: ' + process.stderr.read())
            try:
                with urllib.request.urlopen(base + '/api/status', timeout=1) as response:
                    assert response.status == 200
                break
            except urllib.error.URLError:
                time.sleep(.05)
        else:
            pytest.fail('Dashboard did not start within five seconds')
        yield base
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def test_dashboard_http_and_browser_render_saved_research(dashboard):
    with urllib.request.urlopen(dashboard + '/api/artifacts', timeout=5) as response:
        payload = json.load(response)
    assert {g['expiry'] for g in payload['groups']} == {'2026-10-08', '2026-11-07'}
    assert payload['plans']
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1400, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            response = page.goto(dashboard + '/?u=SYNTH&e=2026-10-08')
            assert response.status == 200
            page.wait_for_function("document.querySelectorAll('canvas').length > 0")
            assert 'SYNTH' in page.inner_text('body')
            assert 'structure comparison' in page.inner_text('body').lower()
            assert not errors
        finally:
            browser.close()


def test_dashboard_missing_static_file_is_404_and_server_recovers(dashboard):
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(dashboard + '/static/missing.js', timeout=5)
    assert caught.value.code == 404
    with urllib.request.urlopen(dashboard + '/api/status', timeout=5) as response:
        assert response.status == 200
