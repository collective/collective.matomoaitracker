"""Varnish in front of Nginx and Plone."""

from .helpers import BROWSER
from .helpers import new_marker

import re


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
    x_varnish = stack.get(marker).headers["X-Varnish"]

    # A hit shows the transaction ids of the request and of the cached object.
    assert re.fullmatch(r"\d+ \d+", x_varnish)


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
