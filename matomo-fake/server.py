"""A fake Matomo bulk tracking endpoint for the Docker test stack.

POST /matomo.php       Matomo bulk tracking request, recorded when token_auth
                       matches FAKE_MATOMO_TOKEN_AUTH.
POST /index.php        The reporting API methods the control panel's "Test
                       connection" calls: sites 1 and 2, custom dimensions 1
                       to 3 of site 2.
GET /_requests         The recorded tracking requests, as JSON.
DELETE /_requests      Forget the recorded tracking requests.
"""

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qsl

import json
import os
import threading
import time


TOKEN_AUTH = os.environ.get("FAKE_MATOMO_TOKEN_AUTH", "test-token")
recorded = []
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path == "/index.php":
            return self.reply(200, self.api())
        if self.path != "/matomo.php":
            return self.reply(404, {"status": "error"})
        try:
            bulk = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests = bulk["requests"]
        except (ValueError, KeyError, TypeError):
            return self.reply(400, {"status": "error", "message": "invalid body"})
        if bulk.get("token_auth") != TOKEN_AUTH:
            return self.reply(401, {"status": "error", "message": "invalid token"})
        with lock:
            for request in requests:
                params = dict(parse_qsl(request.lstrip("?")))
                params["_received"] = time.time()
                recorded.append(params)
        self.reply(
            200,
            {
                "status": "success",
                "tracked": len(requests),
                "invalid": 0,
                "invalid_indices": [],
            },
        )

    def api(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        params = dict(parse_qsl(body))
        if params.get("token_auth") != TOKEN_AUTH:
            return {"result": "error", "message": "You must be logged in"}
        site_id = params.get("idSite")
        if site_id not in ("1", "2"):
            return {"result": "error", "message": f"The site id {site_id} is invalid"}
        method = params.get("method")
        if method == "SitesManager.getSiteFromId":
            return {"idsite": site_id, "name": f"Fake site {site_id}"}
        if method == "CustomDimensions.getConfiguredCustomDimensions":
            return [
                {
                    "idcustomdimension": 1,
                    "name": "AI bot category",
                    "scope": "visit",
                    "active": True,
                },
                {
                    "idcustomdimension": 2,
                    "name": "Cache status",
                    "scope": "action",
                    "active": True,
                },
                {
                    "idcustomdimension": 3,
                    "name": "AI bot name",
                    "scope": "action",
                    "active": True,
                },
            ]
        return {"result": "error", "message": f"Unknown method {method}"}

    def do_GET(self):
        if self.path != "/_requests":
            return self.reply(404, {"status": "error"})
        with lock:
            self.reply(200, list(recorded))

    def do_DELETE(self):
        if self.path != "/_requests":
            return self.reply(404, {"status": "error"})
        with lock:
            recorded.clear()
        self.reply(200, [])

    def log_message(self, format, *args):  # noqa: A002 - name of the base class
        print(format % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("", 8000), Handler).serve_forever()
