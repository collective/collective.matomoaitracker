"""Matomo tracking browser view."""

from collective.matomoaitracker import logger
from http.client import HTTPConnection
from http.client import HTTPSConnection
from json import dumps
from json import loads
from plone import api
from Products.Five.browser import BrowserView
from urllib.parse import urlencode
from urllib.parse import urljoin
from urllib.parse import urlparse


class MatomoVarnishLogConsumerView(BrowserView):
    """Accept Varnish AI request events and forward them to Matomo."""

    max_events = 100
    max_source_url_length = 4096
    max_user_agent_length = 1024

    def __call__(self):
        if self.request.method != "POST":
            self.request.response.setHeader("Allow", "POST")
            return self._json_response(405, {"error": "POST required"})

        try:
            payload = loads(self.request.get("BODY", b""))
        except (TypeError, ValueError):
            return self._json_response(400, {"error": "Invalid JSON body"})

        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list) or not events:
            return self._json_response(
                400, {"error": "Expected a non-empty events list"}
            )
        if len(events) > self.max_events:
            return self._json_response(413, {"error": "Too many events"})
        if not all(self._is_valid_event(event) for event in events):
            return self._json_response(400, {"error": "Invalid event"})

        results = [self._track(event["url"], event["user_agent"]) for event in events]
        return self._json_response(200, {"results": results})

    def _json_response(self, status, payload):
        self.request.response.setStatus(status)
        self.request.response.setHeader("Content-Type", "application/json")
        self.request.response.setHeader("Cache-Control", "no-store")
        return dumps(payload)

    def _is_valid_event(self, event):
        if not isinstance(event, dict):
            return False
        source_url = event.get("url")
        user_agent = event.get("user_agent")
        if (
            not isinstance(source_url, str)
            or not source_url
            or len(source_url) > self.max_source_url_length
            or not isinstance(user_agent, str)
            or not user_agent
            or len(user_agent) > self.max_user_agent_length
        ):
            return False
        try:
            parsed_url = urlparse(source_url)
            port = parsed_url.port
            return (
                parsed_url.scheme in {"http", "https"}
                and parsed_url.hostname is not None
                and (port is None or 0 < port <= 65535)
            )
        except ValueError:
            return False

    def _track(self, source_url, user_agent):
        matomo_site_id = api.portal.get_registry_record(
            "matomoaitracker.matomo_site_id"
        )
        matomo_base_url = api.portal.get_registry_record(
            "matomoaitracker.matomo_base_url"
        )
        if matomo_base_url is None or matomo_site_id is None:
            logger.warning("Matomo settings are not configured")
            return False
        endpoint = urljoin(
            matomo_base_url.rstrip("/") + "/",
            "matomo.php",
        )
        parsed_endpoint = urlparse(endpoint)
        if (
            parsed_endpoint.scheme not in {"http", "https"}
            or not parsed_endpoint.netloc
        ):
            logger.warning("Invalid Matomo Base URL: %s", matomo_base_url)
            return False
        payload = urlencode({
            "idsite": matomo_site_id,
            "rec": "1",
            "recMode": "1",
            "url": source_url,
            "ua": user_agent,
        }).encode("ascii")
        connection_class = (
            HTTPSConnection if parsed_endpoint.scheme == "https" else HTTPConnection
        )
        connection = None
        try:
            connection = connection_class(parsed_endpoint.netloc, timeout=2)
            connection.request(
                "POST",
                parsed_endpoint.path or "/",
                body=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response = connection.getresponse()
            response.read()
            return 200 <= response.status < 300
        except (OSError, ValueError):
            logger.warning("Unable to send Matomo tracking request", exc_info=True)
        finally:
            if connection is not None:
                connection.close()
        return False
