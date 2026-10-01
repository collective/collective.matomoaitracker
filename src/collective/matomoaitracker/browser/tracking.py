"""Matomo tracking browser view."""

from collective.matomoaitracker import logger
from http.client import HTTPConnection
from http.client import HTTPSConnection
from plone import api
from Products.Five.browser import BrowserView
from urllib.parse import urlencode
from urllib.parse import urljoin
from urllib.parse import urlparse


class MatomoAIChatbotTrackingView(BrowserView):
    """Send an AI chatbot request to Matomo without changing the page response."""

    def __call__(self):
        source_url = self.request.form.get("url", "")
        user_agent = self.request.getHeader("User-Agent", "")
        if source_url and user_agent:
            self._track(source_url, user_agent)

        self.request.response.setStatus(204)
        self.request.response.setHeader("Cache-Control", "no-store")
        return ""

    def _track(self, source_url, user_agent):
        matomo_site_id = api.portal.get_registry_record(
            "matomoaitracker.matomo_site_id"
        )
        matomo_base_url = api.portal.get_registry_record(
            "matomoaitracker.matomo_base_url"
        )
        if matomo_base_url is None or matomo_site_id is None:
            logger.warning("Matomo settings are not configured")
            return
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
            return
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
        connection = connection_class(parsed_endpoint.netloc, timeout=2)
        try:
            connection.request(
                "POST",
                parsed_endpoint.path or "/",
                body=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            connection.getresponse().read()
        except (OSError, ValueError):
            logger.warning("Unable to send Matomo tracking request", exc_info=True)
        finally:
            connection.close()
