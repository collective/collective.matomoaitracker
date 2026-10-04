"""Helpers for the stack tests, see conftest.py."""

from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener
from urllib.request import HTTPRedirectHandler
from urllib.request import Request

import base64
import json
import os
import subprocess
import time
import uuid


ROOT = Path(__file__).parents[2]
FAKE_MATOMO = "http://matomo:8000"
# Seconds to wait for tracking requests to arrive in Matomo.
DELIVERY_TIMEOUT = 30
# Seconds Varnish may cache pages with the moderateCaching policy.
SMAXAGE = 60
OPERATION_MAPPING = "plone.caching.interfaces.ICacheSettings.operationMapping"
MODERATE_SMAXAGE = "plone.app.caching.moderateCaching.smaxage"
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Firefox/140.0"


def compose(*args, check=True):
    """Run docker compose in the project, return its output."""
    result = subprocess.run(  # noqa: S603 - fixed command, no shell
        ["docker", "compose", *args],  # noqa: S607 - docker from PATH
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def published_port(service, port):
    output = compose("port", service, str(port), check=False)
    return output.rsplit(":", 1)[-1] if output else None


@dataclass
class Response:
    status: int
    headers: Message
    body: str
    elapsed: float


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def fetch(url, user_agent=BROWSER, headers=None, method="GET", data=None, auth=None):
    """Request a URL, never following redirects."""
    request = Request(  # noqa: S310 - only http URLs of the stack
        url, data=data, method=method, headers={"User-Agent": user_agent}
    )
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    if auth:
        request.add_header(
            "Authorization", "Basic " + base64.b64encode(auth.encode()).decode()
        )
    start = time.perf_counter()
    try:
        with build_opener(NoRedirects).open(request, timeout=10) as response:
            body = response.read().decode("utf-8", "replace")
            status, response_headers = response.status, response.headers
    except HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        status, response_headers = error.code, error.headers
    return Response(status, response_headers, body, time.perf_counter() - start)


def new_marker():
    return f"stacktest{uuid.uuid4().hex}"


class Stack:
    def __init__(self, varnish_port, plone_port, matomo_port):
        self.varnish_port = varnish_port
        self.varnish_url = f"http://localhost:{varnish_port}"
        self.plone_site_url = f"http://localhost:{plone_port}/Plone"
        self.matomo_url = f"http://localhost:{matomo_port}"
        self.admin = os.environ.get("PLONE_ADMIN", "admin:admin")

    def get(self, marker, path="/", user_agent=BROWSER, headers=None):
        """Request a page through Varnish, with the marker in its URL."""
        return fetch(
            f"{self.varnish_url}{path}?marker={marker}",
            user_agent=user_agent,
            headers=headers,
        )

    def tracked(self, marker):
        """The tracking requests Matomo received for a marker."""
        requests = json.loads(fetch(f"{self.matomo_url}/_requests").body)
        return [request for request in requests if marker in request.get("url", "")]

    def wait_tracked(self, marker, count, timeout=DELIVERY_TIMEOUT):
        """Wait until `count` tracking requests arrived for a marker."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                tracked = self.tracked(marker)
            except OSError:
                # Matomo is (re)starting.
                tracked = []
            if len(tracked) >= count or time.monotonic() > deadline:
                return tracked
            time.sleep(0.5)

    def registry_get(self, name):
        response = fetch(
            f"{self.plone_site_url}/@registry/{name}",
            headers={"Accept": "application/json"},
            auth=self.admin,
        )
        assert response.status == 200, f"Reading {name}: {response.status}"
        return json.loads(response.body)

    def registry_set(self, values):
        response = fetch(
            f"{self.plone_site_url}/@registry",
            method="PATCH",
            data=json.dumps(values).encode(),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            auth=self.admin,
        )
        assert response.status == 204, f"Changing the registry: {response.status}"


def summary(tracked):
    """Tracking requests as sorted (idsite, mode, category, cache) tuples.

    mode is "chatbot" for Matomo's AI Chatbots report (recMode=1), and
    "visit" for the AI bots site (bots=1).
    """
    return sorted(
        (
            int(request["idsite"]),
            "chatbot" if request.get("recMode") == "1" else "visit",
            request.get("dimension1"),
            request.get("dimension2"),
        )
        for request in tracked
    )


def expected(category, cache="miss"):
    """The tracking requests for one request of a bot in a category."""
    visit = (2, "visit", category, cache)
    if category == "user":
        return [(1, "chatbot", None, None), visit]
    return [visit]
