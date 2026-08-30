"""The dashboard application layer: payload assembly and static serving."""

import json

import pytest

from optiondesk.artifacts import write_json
from optiondesk.dashboard import app as app_module


def test_build_payload_adds_the_series_and_the_disclaimer(tmp_path):
    """Catches the page being handed a payload it cannot render.

    render reads series and disclaimer directly, so either one missing is a
    KeyError on every request rather than a degraded page.
    """
    payload = app_module.build_payload(str(tmp_path))

    assert payload["series"] == {"calls": [], "puts": []}
    assert "not investment advice" in payload["disclaimer"]
    assert payload["artifact_dir"] == str(tmp_path)


def test_build_payload_selects_the_requested_group(tmp_path):
    """Catches the query parameters never reaching selection.

    They are what makes each view addressable; ignored, every link lands on
    the newest group.
    """
    for expiry in ("2026-09-18", "2026-10-16"):
        write_json({"underlying": "TEST", "expiry": expiry, "spot": 100.0,
                    "meta": {}, "units": {"delta": "a", "vega": "b",
                                          "theta": "c"}, "rows": []},
                   "greeks_TEST_{}.json".format(expiry), tmp_path)

    payload = app_module.build_payload(str(tmp_path), "TEST", "2026-09-18")
    assert payload["selected"]["expiry"] == "2026-09-18"
    assert payload["ladder"]["expiry"] == "2026-09-18"


def test_status_reports_the_engine_and_the_artifact_directory(tmp_path):
    """Catches the status endpoint losing what a client checks it for."""
    status = app_module.status_payload(str(tmp_path))

    assert set(status["engine"]) >= {"available", "package", "version",
                                     "license", "message"}
    assert status["artifact_dir"] == str(tmp_path)
    assert "not investment advice" in status["disclaimer"]


def test_the_artifact_directory_can_be_set_by_environment(tmp_path,
                                                          monkeypatch):
    """Catches the environment override being ignored.

    It is the documented way to point the dashboard at a directory without
    passing a flag, and silently reading the default instead would show a
    user someone else's artifacts.
    """
    monkeypatch.setenv("OPTIONDESK_ARTIFACTS", str(tmp_path))
    assert app_module.status_payload()["artifact_dir"] == str(tmp_path)
    # An explicit argument still outranks the environment.
    other = tmp_path / "explicit"
    assert app_module.status_payload(str(other))["artifact_dir"] == str(other)


def test_render_index_returns_a_whole_document(tmp_path):
    """Catches a fragment being served where a document is expected."""
    html = app_module.render_index(str(tmp_path))

    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "/static/echarts.min.js" in html


def test_the_vendored_bundle_is_served_with_a_script_content_type(tmp_path):
    """Catches the chart library being served as something a browser will
    not execute.

    The bundle is vendored so the dashboard works offline; a wrong content
    type silently leaves every chart blank.
    """
    body, content_type = app_module._static_bytes("echarts.min.js")

    assert body is not None and len(body) > 1000
    assert content_type == "application/javascript; charset=utf-8"


@pytest.mark.parametrize("name", [
    "../style.py",             # a real file one level up
    "../../artifacts.py",      # a real file two levels up
    "/etc/hosts",              # absolute, which Path join would honour
    "does-not-exist.js",
])
def test_static_serving_refuses_anything_outside_its_directory(name):
    """Catches a crafted URL reading a file the server never meant to expose.

    Path joining honours an absolute component and .. walks upward, so the
    resolved path has to be checked against the static root rather than the
    string being inspected.
    """
    assert app_module._static_bytes(name) == (None, None)


def test_the_dashboard_never_writes_to_the_artifact_directory(tmp_path):
    """Catches the reader acquiring a write path.

    It reads artifacts and holds no state, which is what makes it safe to
    refresh during a run that is still writing.
    """
    write_json({"underlying": "TEST", "expiry": "2026-09-18", "spot": 100.0,
                "meta": {}}, "chain_TEST_2026-09-18.json", tmp_path)
    before = {p.name: p.stat().st_mtime for p in tmp_path.iterdir()}

    app_module.render_index(str(tmp_path))
    app_module.build_payload(str(tmp_path))
    app_module.status_payload(str(tmp_path))

    after = {p.name: p.stat().st_mtime for p in tmp_path.iterdir()}
    assert after == before


def test_the_fastapi_application_exposes_the_documented_routes(tmp_path):
    """Catches a route disappearing from the full application.

    The stdlib fallback serves the same three paths, so a client written
    against one has to work against the other.
    """
    pytest.importorskip("fastapi")
    app = app_module.build_app(str(tmp_path))
    paths = {route.path for route in app.routes}

    assert {"/", "/api/status", "/api/artifacts", "/static/{name}"} <= paths
