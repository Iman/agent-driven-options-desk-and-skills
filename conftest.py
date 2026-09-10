"""Assign each test to one layer; unit runs cannot start external processes."""
from pathlib import Path
import socket
import subprocess

import pytest

INTEGRATION = {
    'test_container.py', 'test_dashboard_server.py', 'test_installer.py',
    'test_run_script.py',
}
VALIDATION = {
    'test_documented_counts.py', 'test_runtime_docs.py', 'test_packaging.py',
    'test_screenshots.py', 'test_house_rules.py', 'test_documented_evidence.py',
    'test_license_claims.py', 'test_coverage_gate.py', 'test_wiki.py',
}
LAYERS = {'unit', 'bdd', 'integration', 'validation'}


def pytest_collection_modifyitems(items):
    for item in items:
        path = Path(str(item.path))
        if 'bdd' in path.parts:
            layer = 'bdd'
        elif 'integration' in path.parts or path.name in INTEGRATION:
            layer = 'integration'
        elif path.name in VALIDATION:
            layer = 'validation'
        else:
            layer = 'unit'
        existing = {mark.name for mark in item.iter_markers()} & LAYERS
        if existing and existing != {layer}:
            raise pytest.UsageError('Conflicting test layers for ' + item.nodeid)
        item.add_marker(getattr(pytest.mark, layer))


@pytest.fixture(autouse=True)
def isolate_unit_boundaries(request, monkeypatch):
    if request.node.get_closest_marker('unit') is None:
        return

    def refused(*args, **kwargs):
        pytest.fail('Unit tests must replace external I/O or use the integration layer')

    monkeypatch.setattr(subprocess, 'Popen', refused)
    monkeypatch.setattr(socket.socket, 'connect', refused)
    monkeypatch.setattr(socket.socket, 'connect_ex', refused)
    monkeypatch.setattr(socket.socket, 'bind', refused)
