"""Outages of Matomo or the shipper delay tracking, they do not lose it."""

from .helpers import compose
from .helpers import expected
from .helpers import new_marker
from .helpers import summary

import pytest
import time


@pytest.fixture
def stopped():
    """Stop services, and always start them again afterwards."""
    services = []

    def stop(service):
        services.append(service)
        compose("stop", service)

    yield stop
    if services:
        compose("start", *services)


def test_matomo_down(stack, stopped):
    marker = new_marker()
    stopped("matomo")

    response = stack.get(marker, user_agent="GPTBot/1.1")
    assert response.status == 200
    time.sleep(5)
    compose("start", "matomo")

    # The shipper backs off while Matomo is down, up to 5 minutes.
    assert summary(stack.wait_tracked(marker, 1, timeout=60)) == expected("training")


def test_shipper_restart(stack, stopped):
    marker = new_marker()
    stopped("shipper")

    stack.get(marker, user_agent="Claude-User/1.0")
    compose("start", "shipper")

    assert summary(stack.wait_tracked(marker, 2)) == expected("user")
    # Nothing is shipped twice after the restart.
    time.sleep(3)
    assert len(stack.tracked(marker)) == 2
