"""Receive AI bot requests from the shipper and forward them to Matomo."""

from collective.matomoaitracker import logger
from collective.matomoaitracker.bots import classify
from collective.matomoaitracker.bots import USER
from contextlib import suppress
from http.client import HTTPConnection
from http.client import HTTPSConnection
from ipaddress import ip_address
from json import dumps
from json import loads
from plone import api
from Products.Five.browser import BrowserView
from urllib.parse import urlencode
from urllib.parse import urljoin
from urllib.parse import urlparse

import os


TOKEN_AUTH_ENVIRONMENT_VARIABLE = "MATOMO_AI_TOKEN_AUTH"  # noqa: S105 - a name
CACHE_STATUSES = frozenset(("hit", "miss", "pass", "pipe", "synth"))
MAX_EVENTS = 500
MAX_URL_LENGTH = 4096
MAX_USER_AGENT_LENGTH = 1024
MATOMO_TIMEOUT = 30


class MatomoError(Exception):
    """Matomo did not accept the bulk request."""


def registry_record(name):
    return api.portal.get_registry_record(f"matomoaitracker.{name}", default=None)


class MatomoAIChatbotTrackingView(BrowserView):
    """Forward a batch of AI bot requests to the Matomo bulk tracking API.

    The view is called by the shipper with a JSON body
    ``{"events": [...]}``.  Each event describes one request Varnish
    delivered to an AI bot:

    - ``time``: Unix timestamp of the request (required)
    - ``url``: full URL of the requested page (required)
    - ``user_agent``: User-Agent of the bot (required)
    - ``ip``, ``referrer``, ``status``, ``bytes``, ``duration_ms`` and
      ``cache`` (how Varnish handled it: hit, miss, pass, ...): optional

    AI assistants (category ``user``) are tracked in Matomo's AI Chatbots
    report of the Matomo site.  When an AI bots site is configured, every AI
    bot request is also tracked there as a visit, with the bot category and
    cache status as custom dimensions.

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

        settings = self.settings()
        if settings is None:
            return self.reply(503, {"error": "Matomo is not configured"})

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
            return self.reply(502, {"error": "Matomo did not accept the requests"})

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

    def settings(self):
        """Return the Matomo settings, or None when they are incomplete."""
        base_url = registry_record("matomo_base_url")
        site_id = registry_record("matomo_site_id")
        token_auth = os.environ.get(TOKEN_AUTH_ENVIRONMENT_VARIABLE)
        if not base_url or not site_id or not token_auth:
            logger.warning(
                "Matomo Base URL, Site ID or %s is not configured",
                TOKEN_AUTH_ENVIRONMENT_VARIABLE,
            )
            return None
        endpoint = urlparse(urljoin(base_url.rstrip("/") + "/", "matomo.php"))
        if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
            logger.warning("Invalid Matomo Base URL: %s", base_url)
            return None
        return {
            "endpoint": endpoint,
            "token_auth": token_auth,
            "site_id": site_id,
            "bot_site_id": registry_record("matomo_bot_site_id"),
            "dimension_category": registry_record("matomo_dimension_category"),
            "dimension_cache": registry_record("matomo_dimension_cache"),
        }

    def matomo_requests(self, event, settings):
        """Return the Matomo tracking requests for one event, if valid."""
        event = self.validate(event)
        if event is None:
            return []
        _bot_name, category = classify(event["user_agent"])
        common = {
            "rec": "1",
            "send_image": "0",
            "url": event["url"],
            "ua": event["user_agent"],
            "cdt": str(event["time"]),
        }
        requests = []
        if category == USER:
            # Matomo's AI Chatbots report (BotTracking, Matomo 5.8+).
            params = {**common, "idsite": settings["site_id"], "recMode": "1"}
            optional = {
                "http_status": event.get("status"),
                "bw_bytes": event.get("bytes"),
                "pf_srv": event.get("duration_ms"),
            }
            params.update({k: v for k, v in optional.items() if v is not None})
            requests.append(params)
        if settings["bot_site_id"]:
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
        return values

    def send(self, settings, matomo_requests):
        """Send the requests to Matomo, return how many it rejected."""
        if not matomo_requests:
            return 0
        endpoint = settings["endpoint"]
        body = dumps({
            "requests": matomo_requests,
            "token_auth": settings["token_auth"],
        }).encode("utf-8")
        connection_class = (
            HTTPSConnection if endpoint.scheme == "https" else HTTPConnection
        )
        connection = connection_class(endpoint.netloc, timeout=MATOMO_TIMEOUT)
        try:
            connection.request(
                "POST",
                endpoint.path or "/",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response_body = response.read()
        except OSError as error:
            raise MatomoError(error) from error
        finally:
            connection.close()

        if response.status != 200:
            raise MatomoError(f"HTTP {response.status}")
        try:
            result = loads(response_body)
        except ValueError as error:
            raise MatomoError("Response is not JSON") from error
        if not isinstance(result, dict) or result.get("status") != "success":
            raise MatomoError(f"Unexpected response: {response_body[:200]!r}")
        rejected = result.get("invalid", 0)
        if rejected:
            logger.warning(
                "Matomo rejected %s tracking request(s): %s",
                rejected,
                result.get("invalid_indices"),
            )
        return rejected if isinstance(rejected, int) else 0
