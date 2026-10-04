"""A fake Matomo bulk tracking endpoint for the Docker test stack.

POST /matomo.php       Matomo bulk tracking request, recorded when token_auth
                       matches FAKE_MATOMO_TOKEN_AUTH.
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

    def log_message(self, message_format, *args):
        print(message_format % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("", 8000), Handler).serve_forever()
