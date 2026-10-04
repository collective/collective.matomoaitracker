"""Varnish in front of Nginx and Plone."""

from .helpers import BROWSER
from .helpers import fetch
from .helpers import new_marker

import json
import pytest
import re
import time


# Ports blocked by Chrome and Firefox, see net/base/port_util.cc in Chromium.
BROWSER_BLOCKED_PORTS = {
    1719, 1720, 1723, 2049, 3659, 4045, 4190, 5060, 5061, 6000, 6566,
    6665, 6666, 6667, 6668, 6669, 6679, 6697, 10080,
}  # fmt: skip


def test_served_by_varnish(stack, caching_policy):
    response = stack.get(new_marker())

    assert response.status == 200
    assert "varnish" in response.headers.get("Via", "").lower()


def test_port_can_be_opened_in_a_browser(stack):
    assert int(stack.varnish_port) not in BROWSER_BLOCKED_PORTS, (
        "Chrome and Firefox block this port, set VARNISH_PORT in .env"
    )


def test_virtualhostmonster_links(stack, caching_policy):
    body = stack.get(new_marker()).body

    assert f'href="{stack.varnish_url}/' in body
    assert "VirtualHostBase" not in body


def test_second_request_is_a_cache_hit(stack, caching_policy):
    caching_policy.require_caching()
    marker = new_marker()

    stack.get(marker)
    assert is_hit(stack.get(marker))


def test_bots_are_as_fast_as_browsers(stack, caching_policy):
    """Tracking adds nothing to the request path, also not for bots."""
    marker = new_marker()
    stack.get(marker)

    def average(user_agent):
        times = [stack.get(marker, user_agent=user_agent).elapsed for _ in range(20)]
        return sum(times) / len(times)

    bot, browser = average("GPTBot/1.1"), average(BROWSER)

    # Generous margins: without caching every request renders a Plone page.
    assert bot <= browser * 1.25 + 0.005, f"{bot:.4f}s vs {browser:.4f}s per request"


def is_hit(response):
    """A hit shows the transaction ids of the request and of the cached object."""
    return re.fullmatch(r"\d+ \d+", response.headers["X-Varnish"]) is not None


def test_purge_clears_the_cache(stack, caching_policy):
    caching_policy.require_caching()
    marker = new_marker()
    stack.get(marker)
    assert is_hit(stack.get(marker))

    # The tests run on the Docker host, which is in a private network.
    purged = fetch(f"{stack.varnish_url}/?marker={marker}", method="PURGE")

    assert purged.status == 200
    assert not is_hit(stack.get(marker))


@pytest.fixture
def page(stack):
    """A published news item, created and removed through Varnish as admin.

    By default plone.app.caching purges File, Image and News Item, not pages.
    """
    page_id = new_marker()
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    def call(method, path="", payload=None):
        return fetch(
            f"{stack.varnish_url}{path}",
            method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
            auth=stack.admin,
        )

    created = call(
        "POST", payload={"@type": "News Item", "id": page_id, "title": "Old"}
    )
    assert created.status == 201, f"Creating the page: {created.status}"
    assert call("POST", f"/{page_id}/@workflow/publish").status == 200
    yield f"/{page_id}", call
    call("DELETE", f"/{page_id}")


def test_plone_purges_changed_content(stack, caching_policy, page):
    """Editing content makes Plone purge it from Varnish (plone.cachepurging)."""
    caching_policy.require_caching()
    path, call = page
    url = f"{stack.varnish_url}{path}"
    fetch(url)
    assert is_hit(fetch(url))

    # Through Varnish, like an editor: Plone purges the public paths.
    assert call("PATCH", path, {"title": "New title"}).status == 204

    # Plone purges in a background thread.
    deadline = time.monotonic() + 10
    while is_hit(response := fetch(url)) and time.monotonic() < deadline:
        time.sleep(0.5)
    assert not is_hit(response)
    assert "New title" in response.body
