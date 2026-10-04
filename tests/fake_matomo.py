"""A fake Matomo on a random local port, for the Plone tests."""

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from json import dumps
from json import loads
from threading import Thread
from urllib.parse import parse_qsl


class FakeMatomo:
    """Matomo's bulk tracking endpoint and a few reporting API methods.

    The reporting API knows sites 1 and 2, and custom dimensions 3 and 5
    (active) and 4 (inactive) of site 2.
    """

    def __init__(self):
        self.bulk_requests = []
        self.api_calls = []
        self.status = 200
        # Answer to bulk tracking requests, instead of the default success.
        self.response: dict | None = None
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if self.path.endswith("/index.php"):
                    return self.reply(fake.api(dict(parse_qsl(body.decode()))))
                bulk = loads(body)
                fake.bulk_requests.append(bulk)
                self.reply(
                    fake.response
                    or {
                        "status": "success",
                        "tracked": len(bulk["requests"]),
                        "invalid": 0,
                    }
                )

            def reply(self, response):
                payload = dumps(response).encode()
                self.send_response(fake.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):  # noqa: A002 - as in the base class
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        Thread(target=self.server.serve_forever, daemon=True).start()

    def api(self, params):
        self.api_calls.append(params)
        if params.get("token_auth") != "secret":
            return {"result": "error", "message": "You must be logged in"}
        method, site_id = params.get("method"), params.get("idSite")
        if site_id not in ("1", "2"):
            return {"result": "error", "message": f"The site id {site_id} is invalid"}
        if method == "SitesManager.getSiteFromId":
            return {"idsite": site_id, "name": f"Site {site_id}"}
        if method == "CustomDimensions.getConfiguredCustomDimensions":
            return [
                {
                    "idcustomdimension": 3,
                    "name": "Bot category",
                    "scope": "visit",
                    "active": True,
                },
                {
                    "idcustomdimension": 4,
                    "name": "Cache",
                    "scope": "action",
                    "active": False,
                },
                {
                    "idcustomdimension": 5,
                    "name": "Bot name",
                    "scope": "action",
                    "active": True,
                },
            ]
        return {"result": "error", "message": f"Unknown method {method}"}

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    @property
    def tracked(self):
        """All tracking requests received, as dictionaries."""
        return [
            dict(parse_qsl(request.lstrip("?")))
            for bulk in self.bulk_requests
            for request in bulk["requests"]
        ]
