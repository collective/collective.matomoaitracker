"""Receive AI bot requests from the shipper and forward them to Matomo."""

from collective.matomoaitracker import logger
from collective.matomoaitracker.bots import CATEGORIES
from collective.matomoaitracker.bots import classify
from collective.matomoaitracker.bots import USER
from collective.matomoaitracker.status import STATUS
from contextlib import suppress
from functools import lru_cache
from ipaddress import ip_address
from json import dumps
from json import loads
from plone import api
from Products.Five.browser import BrowserView
from urllib.parse import urlencode
from urllib.parse import urlparse

import os
import re
import requests


TOKEN_AUTH_ENVIRONMENT_VARIABLE = "MATOMO_AI_TOKEN_AUTH"  # noqa: S105 - a name
CACHE_STATUSES = frozenset(("hit", "miss", "pass", "pipe", "synth"))
MAX_EVENTS = 500
MAX_URL_LENGTH = 4096
MAX_USER_AGENT_LENGTH = 1024
MATOMO_TIMEOUT = 30
MAX_CONTENT_TYPE_LENGTH = 255
# Sent as `source` with requests for Matomo's AI Chatbots report, like
# Matomo's own trackers send "wordpress" or "Cloudflare".
SOURCE = "Varnish"
# Responses of these types are pages or parts of pages, not documents.
NOT_DOCUMENTS = frozenset((
    "application/atom+xml",
    "application/javascript",
    "application/json",
    "application/ld+json",
    "application/manifest+json",
    "application/rss+xml",
    "application/xhtml+xml",
    "application/xml",
))


class MatomoError(Exception):
    """Matomo did not accept the bulk request."""


def registry_record(name):
    return api.portal.get_registry_record(f"matomoaitracker.{name}", default=None)


def token_auth_setting():
    """Return the Matomo token, and whether it comes from the environment."""
    from_environment = os.environ.get(TOKEN_AUTH_ENVIRONMENT_VARIABLE)
    if from_environment:
        return from_environment, True
    return registry_record("matomo_token_auth") or "", False


def load_settings():
    """Return the Matomo settings and "", or None and what is missing."""
    base_url = registry_record("matomo_base_url")
    site_id = registry_record("matomo_site_id")
    token_auth = token_auth_setting()[0]
    problem = ""
    if not base_url or not site_id:
        problem = "The Matomo Base URL or Site ID is not configured"
    elif not token_auth:
        problem = "No Matomo token: paste one in the control panel"
    else:
        base = urlparse(base_url.rstrip("/") + "/")
        if base.scheme not in {"http", "https"} or not base.netloc:
            problem = f"Invalid Matomo Base URL: {base_url}"
    if problem:
        logger.warning(problem)
        return None, problem
    categories = registry_record("matomo_bot_site_categories")
    return {
        "base_url": base_url.rstrip("/") + "/",
        "token_auth": token_auth,
        "site_id": site_id,
        "bot_site_id": registry_record("matomo_bot_site_id"),
        "bot_site_categories": set(CATEGORIES if categories is None else categories),
        "dimension_category": registry_record("matomo_dimension_category"),
        "dimension_cache": registry_record("matomo_dimension_cache"),
        "dimension_bot": registry_record("matomo_dimension_bot"),
        "excluded_urls": compile_patterns(
            tuple(registry_record("matomo_excluded_urls") or ())
        ),
    }, ""


@lru_cache(maxsize=16)
def compile_patterns(patterns):
    """Compile the excluded URL patterns, skipping invalid ones."""
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            logger.warning("Ignoring invalid excluded URL pattern: %s", pattern)
    return compiled


def is_document(content_type, status):
    """Whether a response is a document, like a PDF, rather than a page."""
    if status not in (None, 200, 206) or not content_type:
        return False
    media_type = content_type.split(";")[0].strip().lower()
    if media_type in NOT_DOCUMENTS:
        return False
    main_type = media_type.split("/")[0]
    return main_type in ("application", "audio", "video") or media_type == "text/csv"


class MatomoAIChatbotTrackingView(BrowserView):
    """Forward a batch of AI bot requests to the Matomo bulk tracking API.

    The view is called by the shipper with a JSON body
    ``{"events": [...]}``.  Each event describes one request Varnish
    delivered to an AI bot:

    - ``time``: Unix timestamp of the request (required)
    - ``url``: full URL of the requested page (required)
    - ``user_agent``: User-Agent of the bot (required)
    - ``ip``, ``referrer``, ``status``, ``bytes``, ``duration_ms``,
      ``content_type`` and ``cache`` (how Varnish handled it: hit, miss,
      pass, ...): optional

    AI assistants (category ``user``) are tracked in Matomo's AI Chatbots
    report of the Matomo site.  When an AI bots site is configured, every AI
    bot request is also tracked there as a visit, with the bot category,
    cache status and bot name as custom dimensions.

    Requests for excluded URLs (the resources of pages) are not tracked.
    Documents, like PDFs, are tracked as downloads.

    Responses:

    - 200 when Matomo accepted the batch; events that are not tracked (no
      known AI bot, invalid data, rejected by Matomo) are counted in the
      response, they are not worth retrying.
    - 400 or 413 when the body is invalid, retrying does not help.
    - 502 when Matomo could not be reached or refused the batch, and 503
      when the add-on is not configured: the shipper retries later.
    """

    def __call__(self):
        response = self.request.response
        response.setHeader("Cache-Control", "no-store, private")
        if self.request.method != "POST":
            response.setHeader("Allow", "POST")
            return self.reply(405, {"error": "POST required"})

        try:
            payload = loads(self.request.get("BODY") or b"")
        except (TypeError, ValueError):
            return self.reply(400, {"error": "Invalid JSON body"})
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return self.reply(400, {"error": "Expected an events list"})
        if len(events) > MAX_EVENTS:
            return self.reply(413, {"error": f"At most {MAX_EVENTS} events"})

        if not registry_record("matomo_tracking_enabled"):
            # Switched off: drop the events, the shipper does not retry them.
            STATUS.record_batch(tracked=0, rejected=0, skipped=len(events))
            return self.reply(
                200,
                {"tracked": 0, "rejected": 0, "skipped": len(events), "disabled": True},
            )

        settings, problem = load_settings()
        if settings is None:
            STATUS.record_error(problem)
            return self.reply(503, {"error": problem})

        matomo_requests = []
        skipped = 0
        for event in events:
            event_requests = self.matomo_requests(event, settings)
            if event_requests:
                matomo_requests.extend(event_requests)
            else:
                skipped += 1

        try:
            rejected = self.send(settings, matomo_requests)
        except MatomoError as error:
            logger.warning("Matomo did not accept the tracking requests: %s", error)
            STATUS.record_error(f"Matomo did not accept the requests: {error}")
            return self.reply(502, {"error": "Matomo did not accept the requests"})

        STATUS.record_batch(
            tracked=len(matomo_requests) - rejected, rejected=rejected, skipped=skipped
        )
        return self.reply(
            200,
            {
                "tracked": len(matomo_requests) - rejected,
                "rejected": rejected,
                "skipped": skipped,
            },
        )

    def reply(self, status, payload):
        self.request.response.setStatus(status)
        self.request.response.setHeader("Content-Type", "application/json")
        return dumps(payload)

    def matomo_requests(self, event, settings):
        """Return the Matomo tracking requests for one event, if valid."""
        event = self.validate(event)
        if event is None:
            return []
        path = urlparse(event["url"]).path
        if any(pattern.search(path) for pattern in settings["excluded_urls"]):
            return []
        bot = classify(event["user_agent"])
        if bot is None:
            return []
        bot_name, category = bot
        common = {
            "rec": "1",
            "send_image": "0",
            "url": event["url"],
            "ua": event["user_agent"],
            "cdt": str(event["time"]),
        }
        if is_document(event.get("content_type"), event.get("status")):
            common["download"] = event["url"]
        requests = []
        if category == USER:
            # Matomo's AI Chatbots report (BotTracking, Matomo 5.8+).
            params = {
                **common,
                "idsite": settings["site_id"],
                "recMode": "1",
                "source": SOURCE,
            }
            optional = {
                "http_status": event.get("status"),
                "bw_bytes": event.get("bytes"),
                "pf_srv": event.get("duration_ms"),
            }
            params.update({k: v for k, v in optional.items() if v is not None})
            requests.append(params)
        if settings["bot_site_id"] and category in settings["bot_site_categories"]:
            params = {**common, "idsite": settings["bot_site_id"], "bots": "1"}
            optional = {
                "cip": event.get("ip"),
                "urlref": event.get("referrer"),
                "pf_srv": event.get("duration_ms"),
            }
            if settings["dimension_category"]:
                optional[f"dimension{settings['dimension_category']}"] = category
            if settings["dimension_cache"]:
                optional[f"dimension{settings['dimension_cache']}"] = event.get("cache")
            if settings["dimension_bot"]:
                optional[f"dimension{settings['dimension_bot']}"] = bot_name
            params.update({k: v for k, v in optional.items() if v is not None})
            requests.append(params)
        return ["?" + urlencode(params) for params in requests]

    def validate(self, event):
        """Return the event with checked values, or None when invalid."""
        if not isinstance(event, dict):
            return None
        url = event.get("url")
        user_agent = event.get("user_agent")
        timestamp = event.get("time")
        if (
            not isinstance(url, str)
            or len(url) > MAX_URL_LENGTH
            or not isinstance(user_agent, str)
            or len(user_agent) > MAX_USER_AGENT_LENGTH
            or not isinstance(timestamp, int)
            or isinstance(timestamp, bool)
            or timestamp <= 0
            or classify(user_agent) is None
        ):
            return None
        try:
            parsed_url = urlparse(url)
            parsed_url.port  # noqa: B018 - raises ValueError for invalid ports
        except ValueError:
            return None
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            return None

        return {
            "url": url,
            "user_agent": user_agent,
            "time": timestamp,
            **self.optional_values(event),
        }

    def optional_values(self, event):
        """Return the valid optional values of an event."""
        values = {}
        ip = event.get("ip")
        if isinstance(ip, str):
            with suppress(ValueError):
                values["ip"] = str(ip_address(ip))
        referrer = event.get("referrer")
        if isinstance(referrer, str) and 0 < len(referrer) <= MAX_URL_LENGTH:
            values["referrer"] = referrer
        for name, minimum, maximum in (
            ("status", 100, 599),
            ("bytes", 0, None),
            ("duration_ms", 0, None),
        ):
            value = event.get(name)
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and value >= minimum
                and (maximum is None or value <= maximum)
            ):
                values[name] = value
        if event.get("cache") in CACHE_STATUSES:
            values["cache"] = event["cache"]
        content_type = event.get("content_type")
        if (
            isinstance(content_type, str)
            and len(content_type) <= MAX_CONTENT_TYPE_LENGTH
        ):
            values["content_type"] = content_type
        return values

    def send(self, settings, matomo_requests):
        """Send the requests to Matomo, return how many it rejected."""
        if not matomo_requests:
            return 0
        try:
            response = requests.post(
                settings["base_url"] + "matomo.php",
                json={
                    "requests": matomo_requests,
                    "token_auth": settings["token_auth"],
                },
                timeout=MATOMO_TIMEOUT,
                # A redirect would turn the POST into a GET.
                allow_redirects=False,
            )
        except requests.RequestException as error:
            raise MatomoError(error) from error
        if response.status_code != 200:
            raise MatomoError(f"HTTP {response.status_code}")
        try:
            result = response.json()
        except ValueError as error:
            raise MatomoError("Response is not JSON") from error
        if not isinstance(result, dict) or result.get("status") != "success":
            raise MatomoError(f"Unexpected response: {response.text[:200]!r}")
        rejected = result.get("invalid", 0)
        if rejected:
            logger.warning(
                "Matomo rejected %s tracking request(s): %s",
                rejected,
                result.get("invalid_indices"),
            )
        return rejected if isinstance(rejected, int) else 0
