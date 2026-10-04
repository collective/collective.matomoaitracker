"""Fixtures for testing AI bot tracking end to end against the Docker stack.

    Varnish -> varnishncsa -> ai-bots.log -> shipper -> Plone -> fake Matomo

Run with `make stack-test`, which starts nothing: start the stack first with
`make stack-start`.  Requests go through Varnish, and the tracking requests
are checked in the fake Matomo (matomo-fake/), which records what it gets.
Every test request carries a unique marker in its URL, so tracking requests
can be matched to it.
"""

from .helpers import compose
from .helpers import FAKE_MATOMO
from .helpers import MODERATE_SMAXAGE
from .helpers import new_marker
from .helpers import OPERATION_MAPPING
from .helpers import published_port
from .helpers import SMAXAGE
from .helpers import Stack
from dataclasses import dataclass

import pytest


@pytest.fixture(scope="session")
def stack():
    ports = (
        published_port("varnish", 80),
        published_port("plone", 8080),
        published_port("matomo", 8000),
    )
    if not all(ports):
        pytest.exit("The stack is not running, start it first: make stack-start", 1)
    matomo = compose("exec", "-T", "plone", "printenv", "MATOMO_BASE_URL", check=False)
    if matomo != FAKE_MATOMO:
        pytest.exit(
            f"Plone tracks in {matomo or '?'}, the tests need the fake Matomo. "
            f"Remove MATOMO_BASE_URL from .env, or run: "
            f"MATOMO_BASE_URL={FAKE_MATOMO} make stack-start",
            1,
        )
    stack = Stack(*ports)
    status = stack.get(new_marker()).status
    if status != 200:
        pytest.exit(f"Varnish answered {status}, is Plone still starting?", 1)
    return stack


@dataclass
class CachingPolicy:
    name: str
    cache_control: str

    @property
    def cacheable(self):
        directives = {d.strip().split("=")[0] for d in self.cache_control.split(",")}
        if "s-maxage" in self.cache_control and "s-maxage=0" not in self.cache_control:
            return True
        return not directives & {"private", "no-cache", "no-store", "max-age"}

    def require_caching(self):
        """Skip with the site's policy when Plone forbids caching the page."""
        if not self.cacheable:
            if self.name == "site":
                pytest.skip(f"Plone does not allow caching: {self.cache_control}")
            pytest.fail(f"Varnish may not cache the page: {self.cache_control}")


@pytest.fixture(scope="session", params=["site", "moderate"])
def caching_policy(request, stack):
    """Run tests with the site's caching policy, and with moderateCaching.

    By default Plone does not let Varnish cache pages.  With moderateCaching
    for pages Varnish caches them for SMAXAGE seconds.  The original policy
    is restored afterwards.
    """
    if request.param == "moderate":
        original_mapping = stack.registry_get(OPERATION_MAPPING)
        original_smaxage = stack.registry_get(MODERATE_SMAXAGE)
        mapping = dict(original_mapping)
        for rule in ("plone.content.folderView", "plone.content.itemView"):
            mapping[rule] = "plone.app.caching.moderateCaching"
        stack.registry_set({OPERATION_MAPPING: mapping, MODERATE_SMAXAGE: SMAXAGE})
        request.addfinalizer(
            lambda: stack.registry_set({
                OPERATION_MAPPING: original_mapping,
                MODERATE_SMAXAGE: original_smaxage,
            })
        )
    response = stack.get(new_marker())
    return CachingPolicy(request.param, response.headers.get("Cache-Control", ""))
