"""Local dashboard over the artifacts on disk.

Runs on FastAPI when it is installed and on the standard library HTTP
server when it is not, so a fresh clone can always see its own output.
Both paths serve the same page and the same vendored ECharts bundle.

It reads artifacts and never writes them, so it cannot corrupt a run in
progress, and it holds no state of its own. Refreshing the browser is the
whole update mechanism.
"""

import json
from pathlib import Path

from optiondesk import engine_bridge
from optiondesk.artifacts import DISCLAIMER, artifact_dir
from optiondesk.dashboard import data as data_module
from optiondesk.dashboard import page as page_module

STATIC_DIR = Path(__file__).resolve().parent / "static"


def build_payload(directory=None, underlying=None, expiry=None):
    """Collect every artifact the dashboard renders for one underlying and
    expiry, with the derived series and the disclaimer.
    """
    target = artifact_dir(directory)
    payload = data_module.collect(target, underlying, expiry)
    payload["series"] = data_module.ladder_series(payload["ladder"])
    payload["chain_series"] = data_module.chain_series(payload.get("chain"))
    payload["disclaimer"] = DISCLAIMER
    return payload


def render_index(directory=None, underlying=None, expiry=None):
    """Render the whole dashboard document for one underlying and expiry."""
    return page_module.render(build_payload(directory, underlying, expiry))


def status_payload(directory=None):
    """Report what the server can see: whether the engine is installed, where
    artifacts are read from, and the disclaimer.
    """
    return {
        "engine": engine_bridge.status(),
        "artifact_dir": str(artifact_dir(directory)),
        "disclaimer": DISCLAIMER,
    }


def _static_bytes(name):
    """Serve only from the static directory, and only files that exist.

    Path is resolved and checked against the static root so a crafted URL
    cannot walk out of it.
    """
    candidate = (STATIC_DIR / name).resolve()
    try:
        candidate.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return None, None
    if not candidate.is_file():
        return None, None
    suffix = candidate.suffix.lower()
    content_type = {
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }.get(suffix, "application/octet-stream")
    return candidate.read_bytes(), content_type


def _error_page(exc):
    """What went wrong, in the browser, instead of a dead server."""
    import html as html_module

    return (
        "<!doctype html><html><body style=\"font:14px system-ui;"
        "padding:40px;max-width:70ch\"><h1>The dashboard could not render"
        "</h1><p>One of the artifacts on disk could not be read or "
        "rendered. The server is still running; fix or remove the artifact "
        "and refresh.</p><pre style=\"background:#f4f4f4;padding:12px;"
        "border-radius:6px;overflow-x:auto\">{}: {}</pre></body></html>"
    ).format(html_module.escape(type(exc).__name__),
             html_module.escape(str(exc)))


def build_app(directory=None):
    """FastAPI application, when FastAPI is installed."""
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    app = FastAPI(title="Option desk", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index(u: str = None, e: str = None):
        try:
            return render_index(directory, u, e)
        except Exception as exc:
            return HTMLResponse(_error_page(exc), status_code=500)

    @app.get("/api/status")
    def status():
        return JSONResponse(status_payload(directory))

    @app.get("/api/artifacts")
    def artifacts():
        payload = build_payload(directory)
        return JSONResponse({
            "artifact_dir": payload["artifact_dir"],
            "groups": payload["groups"],
            "selected": payload["selected"],
            "ladder": payload["ladder_path"],
            "exposure": payload["exposure_path"],
            "plans": [p["_path"] for p in payload["plans"]],
        })

    @app.get("/static/{name}")
    def static(name: str):
        body, content_type = _static_bytes(name)
        if body is None:
            raise HTTPException(status_code=404, detail="not found")
        return Response(content=body, media_type=content_type,
                        headers={"Cache-Control": "public, max-age=86400"})

    return app


def serve(host="127.0.0.1", port=8787, directory=None):
    """Start the dashboard. FastAPI when available, stdlib otherwise."""
    try:
        import uvicorn
        from fastapi import FastAPI  # noqa: F401
    except ImportError:
        return _serve_stdlib(host, port, directory)
    uvicorn.run(build_app(directory), host=host, port=port,
                log_level="warning")
    return 0


def _serve_stdlib(host, port, directory):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        server_version = "optiondesk"

        def _send(self, body, content_type, status=200, cache=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if cache:
                self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            underlying = (query.get("u") or [None])[0]
            expiry = (query.get("e") or [None])[0]
            if path.startswith("/static/"):
                body, content_type = _static_bytes(path[len("/static/"):])
                if body is None:
                    self._send(b"not found", "text/plain; charset=utf-8", 404)
                    return
                self._send(body, content_type,
                           cache="public, max-age=86400")
                return
            if path.startswith("/api/status"):
                self._send(json.dumps(status_payload(directory),
                                      indent=1).encode(),
                           "application/json; charset=utf-8")
                return
            if path.startswith("/api/artifacts"):
                payload = build_payload(directory)
                self._send(json.dumps({
                    "artifact_dir": payload["artifact_dir"],
                    "groups": payload["groups"],
                    "selected": payload["selected"],
                    "ladder": payload["ladder_path"],
                    "exposure": payload["exposure_path"],
                    "plans": [p["_path"] for p in payload["plans"]],
                }, indent=1).encode(), "application/json; charset=utf-8")
                return
            try:
                body = render_index(directory, underlying, expiry).encode()
            except Exception as exc:
                # One malformed artifact must not end the server. It
                # previously did: an artifact with no computable R-hat
                # raised inside the renderer and the process died, leaving
                # the port open and every later request unanswered.
                body = _error_page(exc).encode()
                self._send(body, "text/html; charset=utf-8", 500)
                return
            self._send(body, "text/html; charset=utf-8")

        def handle_one_request(self):
            # A client that disconnects mid-response raises here. Without
            # this the traceback goes to stderr and the connection is left
            # in an odd state; there is nothing to do about it but move on.
            try:
                super().handle_one_request()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def log_message(self, *args):
            pass

    # Threading, not the plain HTTPServer. A single-threaded server
    # handles one request at a time, so a client that goes away mid
    # response, or one slow render of a large ladder, wedges the server for
    # every later request. Observed: the page stopped answering entirely
    # after an interrupted request, while the process stayed alive.
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print("dashboard on http://{}:{} (standard library server; install "
          "fastapi and uvicorn for the full app)".format(host, port))
    server.serve_forever()
    return 0
