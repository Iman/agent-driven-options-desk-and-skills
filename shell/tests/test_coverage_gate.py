"""The coverage gate must reject missing evidence and weak individual packages."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def gate():
    path = Path(__file__).resolve().parents[2] / 'scripts/check_unit_coverage.py'
    spec = importlib.util.spec_from_file_location('coverage_gate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report(engine=80, shell=80, agent=80):
    return {'files': {
        f'{package}/src/module.py': {'summary': {
            'covered_lines': covered, 'num_statements': 100}}
        for package, covered in [('engine', engine), ('shell', shell), ('agent', agent)]
    }}


def test_each_package_at_the_threshold_passes(gate):
    rows = gate.assess(report())
    assert len(rows) == 3
    assert all(row['passed'] for row in rows)


def test_strong_packages_cannot_hide_one_below_the_threshold(gate):
    rows = gate.assess(report(engine=100, shell=79, agent=100))
    assert [row['package'] for row in rows if not row['passed']] == ['shell']


def test_rounding_cannot_turn_a_failure_into_a_pass(gate):
    payload = report()
    payload['files']['shell/src/module.py']['summary'] = {
        'covered_lines': 79999, 'num_statements': 100000}
    assert not next(row for row in gate.assess(payload)
                    if row['package'] == 'shell')['passed']


@pytest.mark.parametrize('payload', [{}, {'files': {}}, report(shell=101)])
def test_missing_or_invalid_measurements_fail_closed(gate, payload):
    with pytest.raises(ValueError):
        gate.assess(payload)


def test_a_missing_package_is_not_zero_work(gate):
    payload = report()
    del payload['files']['agent/src/module.py']
    with pytest.raises(ValueError, match='agent'):
        gate.assess(payload)


def test_branch_counts_do_not_change_the_line_gate(gate):
    payload = report()
    for file in payload['files'].values():
        file['summary'].update(num_branches=100, covered_branches=0)
    assert all(row['passed'] for row in gate.assess(payload))


@pytest.mark.parametrize('shell_coverage,missing_file,expected_exit', [
    (80, False, 0), (79, False, 1), (80, True, 1),
])
def test_command_checks_exit_status_and_complete_source_inventory(
        gate, tmp_path, monkeypatch, shell_coverage, missing_file, expected_exit):
    import json
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    payload = report(shell=shell_coverage)
    for name in payload['files']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('value = 1\n')
    if missing_file:
        (tmp_path / 'shell/src/omitted.py').write_text('value = 2\n')
    path = tmp_path / 'coverage.json'
    path.write_text(json.dumps(payload))
    assert gate.main([str(path)]) == expected_exit
