from collective.matomoaitracker.testing import FUNCTIONAL_TESTING
from collective.matomoaitracker.testing import INTEGRATION_TESTING
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from json import dumps
from json import loads
from plone import api
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID
from plone.testing.zope import Browser
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qsl

import os
import transaction


TIME = 1791100000


class FakeMatomo:
    """Matomo bulk tracking endpoint on a random local port."""

    def __init__(self):
        self.bulk_requests = []
        self.status = 200
        self.response = None
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                bulk = loads(body)
                fake.bulk_requests.append(bulk)
                response = fake.response or {
                    "status": "success",
                    "tracked": len(bulk["requests"]),
                    "invalid": 0,
                }
                payload = dumps(response).encode()
                self.send_response(fake.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    @property
    def tracked(self):
        """All tracking requests received, as dictionaries."""
        return [
            dict(parse_qsl(request.lstrip("?")))
            for bulk in self.bulk_requests
            for request in bulk["requests"]
        ]


def event(**overrides):
    values = {
        "time": TIME,
        "url": "https://www.example.org/page?q=1",
        "user_agent": "Mozilla/5.0 (compatible; Claude-User/1.0)",
        "ip": "192.0.2.10",
        "referrer": "https://www.example.org/",
        "status": 200,
        "bytes": 1234,
        "duration_ms": 12,
        "cache": "hit",
    }
    values.update(overrides)
    return values


class TrackingViewTestCase(TestCase):
    layer = INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        self.request = self.layer["request"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.matomo = FakeMatomo()
        self.addCleanup(self.matomo.stop)
        api.portal.set_registry_record("matomoaitracker.matomo_site_id", 1)
        api.portal.set_registry_record(
            "matomoaitracker.matomo_base_url", self.matomo.url + "/"
        )
        environment = patch.dict(os.environ, {"MATOMO_AI_TOKEN_AUTH": "secret"})
        environment.start()
        self.addCleanup(environment.stop)

    def configure_bot_site(self):
        api.portal.set_registry_record("matomoaitracker.matomo_bot_site_id", 2)
        api.portal.set_registry_record("matomoaitracker.matomo_dimension_category", 3)
        api.portal.set_registry_record("matomoaitracker.matomo_dimension_cache", 4)

    def call(self, payload, method="POST"):
        self.request.method = method
        self.request["BODY"] = payload if isinstance(payload, bytes) else dumps(payload)
        view = api.content.get_view("matomoaitracker", self.portal, self.request)
        body = view()
        return self.request.response.getStatus(), loads(body)

    def test_ai_assistant_goes_to_ai_chatbots_report(self):
        status, result = self.call({"events": [event()]})

        self.assertEqual(status, 200)
        self.assertEqual(result, {"tracked": 1, "rejected": 0, "skipped": 0})
        self.assertEqual(self.matomo.bulk_requests[0]["token_auth"], "secret")
        self.assertEqual(
            self.matomo.tracked,
            [
                {
                    "rec": "1",
                    "send_image": "0",
                    "url": "https://www.example.org/page?q=1",
                    "ua": "Mozilla/5.0 (compatible; Claude-User/1.0)",
                    "cdt": str(TIME),
                    "idsite": "1",
                    "recMode": "1",
                    "http_status": "200",
                    "bw_bytes": "1234",
                    "pf_srv": "12",
                }
            ],
        )

    def test_crawlers_are_skipped_without_bot_site(self):
        status, result = self.call({
            "events": [
                event(user_agent="GPTBot/1.1"),
                event(user_agent="PerplexityBot"),
            ]
        })

        self.assertEqual(status, 200)
        self.assertEqual(result, {"tracked": 0, "rejected": 0, "skipped": 2})
        self.assertEqual(self.matomo.bulk_requests, [])

    def test_bot_site_gets_every_category_with_dimensions(self):
        self.configure_bot_site()

        status, result = self.call({
            "events": [
                event(),
                event(user_agent="OAI-SearchBot/1.0", cache="miss"),
                event(user_agent="ClaudeBot/1.0", referrer=None),
            ]
        })

        self.assertEqual(status, 200)
        self.assertEqual(result, {"tracked": 4, "rejected": 0, "skipped": 0})
        tracked = self.matomo.tracked
        self.assertEqual([r["idsite"] for r in tracked], ["1", "2", "2", "2"])
        self.assertEqual(
            tracked[1],
            {
                "rec": "1",
                "send_image": "0",
                "url": "https://www.example.org/page?q=1",
                "ua": "Mozilla/5.0 (compatible; Claude-User/1.0)",
                "cdt": str(TIME),
                "idsite": "2",
                "bots": "1",
                "cip": "192.0.2.10",
                "urlref": "https://www.example.org/",
                "pf_srv": "12",
                "dimension3": "user",
                "dimension4": "hit",
            },
        )
        self.assertEqual(tracked[2]["dimension3"], "search")
        self.assertEqual(tracked[2]["dimension4"], "miss")
        self.assertEqual(tracked[3]["dimension3"], "training")
        self.assertNotIn("urlref", tracked[3])
        self.assertNotIn("recMode", tracked[3])

    def test_invalid_events_are_skipped(self):
        self.configure_bot_site()
        invalid = [
            "not an event",
            event(user_agent="Mozilla/5.0 Firefox/140.0"),
            event(url="ftp://www.example.org/"),
            event(url="https://www.example.org:99999/"),
            event(url="/relative"),
            event(time="1791100000"),
            event(time=True),
            event(user_agent="ClaudeBot " + "x" * 2000),
        ]

        status, result = self.call({"events": [*invalid, event()]})

        self.assertEqual(status, 200)
        self.assertEqual(result["skipped"], len(invalid))
        self.assertEqual(result["tracked"], 2)

    def test_invalid_optional_values_are_left_out(self):
        self.configure_bot_site()

        self.call({
            "events": [
                event(ip="not an ip", status=99, bytes=-1, duration_ms="12", cache="x")
            ]
        })

        for request in self.matomo.tracked:
            for name in ("cip", "http_status", "bw_bytes", "pf_srv", "dimension4"):
                self.assertNotIn(name, request)

    def test_matomo_rejecting_requests_is_reported(self):
        self.matomo.response = {
            "status": "success",
            "tracked": 0,
            "invalid": 1,
            "invalid_indices": [0],
        }

        status, result = self.call({"events": [event()]})

        self.assertEqual(status, 200)
        self.assertEqual(result, {"tracked": 0, "rejected": 1, "skipped": 0})

    def test_matomo_errors_ask_for_a_retry(self):
        for response_status, response in (
            (500, {"status": "error"}),
            (200, {"status": "error", "tracked": 0}),
        ):
            with self.subTest(status=response_status):
                self.matomo.status = response_status
                self.matomo.response = response

                status, _result = self.call({"events": [event()]})

                self.assertEqual(status, 502)

    def test_unreachable_matomo_asks_for_a_retry(self):
        self.matomo.stop()

        status, _result = self.call({"events": [event()]})

        self.assertEqual(status, 502)

    def test_missing_configuration_asks_for_a_retry(self):
        with patch.dict(os.environ, clear=True):
            status, _result = self.call({"events": [event()]})

        self.assertEqual(status, 503)
        self.assertEqual(self.matomo.bulk_requests, [])

    def test_invalid_body_is_refused(self):
        for payload in (b"not json", {"no": "events"}, {"events": "x"}):
            with self.subTest(payload=payload):
                status, _result = self.call(payload)

                self.assertEqual(status, 400)

        status, _result = self.call({"events": [event()] * 501})
        self.assertEqual(status, 413)

    def test_only_post_is_allowed(self):
        status, _result = self.call({"events": [event()]}, method="GET")

        self.assertEqual(status, 405)
        self.assertEqual(self.matomo.bulk_requests, [])

    def test_response_is_not_cacheable(self):
        self.call({"events": [event()]})

        self.assertEqual(
            self.request.response.getHeader("Cache-Control"), "no-store, private"
        )


class TrackingViewSecurityTestCase(TestCase):
    layer = FUNCTIONAL_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        self.matomo = FakeMatomo()
        self.addCleanup(self.matomo.stop)
        api.portal.set_registry_record("matomoaitracker.matomo_site_id", 1)
        api.portal.set_registry_record(
            "matomoaitracker.matomo_base_url", self.matomo.url
        )
        users = self.portal.acl_users
        users.userFolderAddUser("shipper", "shipper-secret", ["Matomo AI Tracker"], [])
        users.userFolderAddUser("member", "member-secret", ["Member"], [])
        transaction.commit()
        environment = patch.dict(os.environ, {"MATOMO_AI_TOKEN_AUTH": "secret"})
        environment.start()
        self.addCleanup(environment.stop)

    def post(self, credentials=None):
        browser = Browser(self.layer["app"])
        browser.raiseHttpErrors = False
        browser.followRedirects = False
        if credentials:
            browser.addHeader("Authorization", f"Basic {credentials}")
        browser.post(
            self.portal.absolute_url() + "/@@matomoaitracker",
            dumps({"events": [event()]}),
            "application/json",
        )
        return browser

    def test_shipper_role_may_submit(self):
        browser = self.post("shipper:shipper-secret")

        self.assertEqual(browser.headers["Status"], "200 OK")
        self.assertEqual(len(self.matomo.tracked), 1)

    def test_anonymous_and_members_may_not_submit(self):
        for credentials in (None, "member:member-secret", "shipper:wrong"):
            with self.subTest(credentials=credentials):
                browser = self.post(credentials)

                # Plone redirects to its login form or answers 401.
                self.assertIn(browser.headers["Status"][:3], ("302", "401"))

        self.assertEqual(self.matomo.bulk_requests, [])
