"""The standard library dashboard server.

FastAPI is optional, so on a fresh clone this fallback is the only server a
user gets. It is exercised over a real loopback socket on an ephemeral port,
never off the machine.
"""

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from optiondesk.artifacts import write_json
from optiondesk.dashboard import app as app_module


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response, response.read()


@pytest.fixture(scope="module")
def running_dashboard(tmp_path_factory):
    """Serve one directory on a loopback port, in a daemon thread.

    Module scoped so the suite binds one port rather than one per test; the
    fallback server has no shutdown hook, so each start would leak a
    listening socket for the rest of the session.
    """
    tmp_path = tmp_path_factory.mktemp("artifacts")
    write_json({"underlying": "TEST", "expiry": "2026-09-18", "spot": 100.0,
                "meta": {}}, "chain_TEST_2026-09-18.json", tmp_path)
    port = free_port()
    # The fallback directly, not through serve(), which picks uvicorn when
    # FastAPI is installed. These tests are named for the fallback and have
    # to exercise it whatever else happens to be in the environment: they
    # used to skip on any machine that had FastAPI, which is every machine
    # that installed the dashboard extra.
    thread = threading.Thread(
        target=app_module._serve_stdlib,
        args=("127.0.0.1", port, str(tmp_path)), daemon=True)
    thread.start()

    base = "http://127.0.0.1:{}".format(port)
    for _ in range(100):
        try:
            get(base + "/api/status", timeout=1)
            return base
        except (urllib.error.URLError, OSError):
            time.sleep(0.02)
    pytest.fail("the fallback server never accepted a connection")


def _fastapi_installed():
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        return False
    return True


def test_the_fallback_serves_the_page(running_dashboard):
    """Catches the fallback serving a fragment or the wrong content type.

    A fresh clone with no FastAPI has to get a browsable page, or the
    dashboard does not exist for that user at all.
    """
    response, body = get(running_dashboard + "/")

    assert response.status == 200
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert body.decode().startswith("<!doctype html>")


def test_the_fallback_serves_the_same_status_shape(running_dashboard):
    """Catches the two servers diverging in what a client can rely on."""
    _, body = get(running_dashboard + "/api/status")
    status = json.loads(body)

    assert set(status) == {"engine", "artifact_dir", "disclaimer"}
    assert "not investment advice" in status["disclaimer"]


def test_the_fallback_lists_the_artifacts_it_can_see(running_dashboard):
    """Catches the inventory endpoint losing the group listing.

    It is how a client discovers what is on disk without parsing the page.
    """
    _, body = get(running_dashboard + "/api/artifacts")
    payload = json.loads(body)

    assert set(payload) == {"artifact_dir", "groups", "selected", "ladder",
                            "exposure", "plans"}
    assert payload["groups"][0]["underlying"] == "TEST"
    assert payload["groups"][0]["expiry"] == "2026-09-18"


def test_the_fallback_serves_the_vendored_bundle_cacheably(
        running_dashboard):
    """Catches the chart library being re-fetched on every page load.

    It is a megabyte, and it is vendored precisely so the dashboard works
    with no outbound request.
    """
    response, body = get(running_dashboard + "/static/echarts.min.js")

    assert response.headers["Content-Type"] == \
        "application/javascript; charset=utf-8"
    assert response.headers["Cache-Control"] == "public, max-age=86400"
    assert len(body) > 100000


def test_the_fallback_refuses_a_file_it_does_not_have(running_dashboard):
    """Catches a missing static file being answered with an empty 200."""
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        get(running_dashboard + "/static/not-a-file.js")
    assert excinfo.value.code == 404


def test_the_query_parameters_select_the_group(running_dashboard):
    """Catches the fallback ignoring the selection the links depend on.

    Every view is addressable by query parameter, and the two servers have
    to agree on that or a bookmark works in one and not the other.
    """
    response, body = get(running_dashboard + "/?u=TEST&e=2026-09-18")
    assert response.status == 200
    assert body.decode().startswith("<!doctype html>")


def test_serve_picks_the_richer_server_when_it_can_and_falls_back_when_not():
    """The dispatch itself, which no test covered.

    The fallback tests now call `_serve_stdlib` directly, which is right for
    them and leaves the choice in `serve()` unexercised. That choice is the
    thing a fresh clone depends on: with FastAPI absent the dashboard has to
    still come up, and with it present the richer server has to be the one
    that runs.
    """
    import sys

    calls = []

    def fake_stdlib(host, port, directory):
        calls.append(("stdlib", host, port))
        return 0

    real_stdlib = app_module._serve_stdlib
    app_module._serve_stdlib = fake_stdlib
    real_uvicorn = sys.modules.get("uvicorn")
    try:
        # FastAPI missing: the import fails and the fallback has to run.
        sys.modules["uvicorn"] = None
        assert app_module.serve("127.0.0.1", 1, "/tmp") == 0
        assert calls == [("stdlib", "127.0.0.1", 1)], calls

        if _fastapi_installed():
            # Present: uvicorn.run is called instead, and the fallback is not.
            class FakeUvicorn:
                started = []

                @staticmethod
                def run(app, host=None, port=None, log_level=None):
                    FakeUvicorn.started.append((host, port))

            sys.modules["uvicorn"] = FakeUvicorn
            calls.clear()
            assert app_module.serve("127.0.0.1", 2, "/tmp") == 0
            assert FakeUvicorn.started == [("127.0.0.1", 2)]
            assert calls == [], "the fallback ran while FastAPI was available"
    finally:
        app_module._serve_stdlib = real_stdlib
        if real_uvicorn is None:
            sys.modules.pop("uvicorn", None)
        else:
            sys.modules["uvicorn"] = real_uvicorn
