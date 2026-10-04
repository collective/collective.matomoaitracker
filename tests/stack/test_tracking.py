"""AI bot requests arrive in Matomo once, in the right category."""

from .helpers import BROWSER
from .helpers import expected
from .helpers import new_marker
from .helpers import summary
from collective.matomoaitracker.bots import BOTS

import pytest
import time


ALL_BOTS = [(bot, category) for category, bots in BOTS.items() for bot in bots]


@pytest.fixture(scope="module")
def bot_requests(stack, caching_policy):
    """Request a page as every bot at once, return the marker per bot.

    Sending them together lets the shipper deliver them in one batch,
    instead of one test after the other waiting for the shipper.
    """
    markers = {}
    for bot, _category in ALL_BOTS:
        markers[bot] = new_marker()
        response = stack.get(
            markers[bot], user_agent=f"Mozilla/5.0 (compatible; {bot}/1.0)"
        )
        assert response.status == 200, f"{bot} got {response.status}"
    return markers


@pytest.mark.parametrize("bot,category", ALL_BOTS)
def test_bot_is_tracked(stack, bot_requests, bot, category):
    tracked = stack.wait_tracked(bot_requests[bot], len(expected(category)))

    assert summary(tracked) == expected(category)
    for request in tracked:
        assert request["ua"] == f"Mozilla/5.0 (compatible; {bot}/1.0)"


def test_user_agent_match_is_case_insensitive(stack, caching_policy):
    marker = new_marker()

    stack.get(marker, user_agent="Mozilla/5.0 (compatible; claudebot/1.0)")

    assert summary(stack.wait_tracked(marker, 1)) == expected("training")


def test_cache_hits_are_tracked(stack, caching_policy):
    caching_policy.require_caching()
    marker = new_marker()

    stack.get(marker, user_agent="ClaudeBot/1.0")
    stack.get(marker, user_agent="ClaudeBot/1.0")

    assert summary(stack.wait_tracked(marker, 2)) == sorted(
        expected("training", "miss") + expected("training", "hit")
    )


def test_tracked_url_and_time(stack, caching_policy):
    marker = new_marker()
    sent = time.time()

    stack.get(
        marker,
        path="/some/page",
        user_agent="GPTBot/1.1",
        headers={"X-Forwarded-Proto": "https"},
    )

    [request] = stack.wait_tracked(marker, 1)
    assert request["url"] == (
        f"https://localhost:{stack.varnish_port}/some/page?marker={marker}"
    )
    # The time of the request, not of shipping it.
    assert int(sent) <= int(request["cdt"]) <= sent + 2


@pytest.mark.parametrize(
    "user_agent,headers",
    [
        (BROWSER, {}),
        ("", {}),
        # A browser cannot make itself count as a bot.
        (BROWSER, {"X-AI-Bot": "user"}),
    ],
    ids=["browser", "no user agent", "browser sending X-AI-Bot"],
)
def test_not_tracked(stack, caching_policy, user_agent, headers):
    marker = new_marker()
    sent_after = new_marker()

    stack.get(marker, user_agent=user_agent, headers=headers)
    # Once a bot request sent afterwards arrived, this one would have too.
    stack.get(sent_after, user_agent="GPTBot/1.1")

    assert stack.wait_tracked(sent_after, 1)
    assert stack.tracked(marker) == []
