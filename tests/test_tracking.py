from collective.matomoaitracker.status import STATUS
from collective.matomoaitracker.testing import FUNCTIONAL_TESTING
from collective.matomoaitracker.testing import INTEGRATION_TESTING
from fake_matomo import FakeMatomo
from json import dumps
from json import loads
from plone import api
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID
from plone.testing.zope import Browser
from typing import Any
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import os
import transaction


TIME = 1791100000


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
        "content_type": "text/html; charset=utf-8",
    }
    values.update(overrides)
    return values


class TrackingViewTestCase(TestCase):
    layer = INTEGRATION_TESTING

    def setUp(self):
        self.portal = cast(Any, self.layer["portal"])
        self.request = cast(Any, self.layer["request"])
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
        STATUS.reset()

    def configure_bot_site(self):
        api.portal.set_registry_record("matomoaitracker.matomo_bot_site_id", 2)
        api.portal.set_registry_record("matomoaitracker.matomo_dimension_category", 3)
        api.portal.set_registry_record("matomoaitracker.matomo_dimension_cache", 4)
        api.portal.set_registry_record("matomoaitracker.matomo_dimension_bot", 5)

    def call(self, payload, method="POST"):
        self.request.method = method
        self.request["BODY"] = payload if isinstance(payload, bytes) else dumps(payload)
        view = cast(
            Any, api.content.get_view("matomoaitracker", self.portal, self.request)
        )
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
                    "source": "Varnish",
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
                "dimension5": "Claude-User",
            },
        )
        self.assertEqual(tracked[2]["dimension3"], "search")
        self.assertEqual(tracked[2]["dimension4"], "miss")
        self.assertEqual(tracked[2]["dimension5"], "OAI-SearchBot")
        self.assertEqual(tracked[3]["dimension3"], "training")
        self.assertEqual(tracked[3]["dimension5"], "ClaudeBot")
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

    def test_resources_of_pages_are_not_tracked(self):
        self.configure_bot_site()
        excluded = [
            "https://www.example.org/++plone++static/plone.css",
            "https://www.example.org/++resource++plone.app.event/event.js",
            "https://www.example.org/++theme++barceloneta/logo.SVG",
            "https://www.example.org/image.png/@@images/image/preview",
            "https://www.example.org/@@images/abc.jpeg",
            "https://www.example.org/fonts/roboto.woff2?v=2",
            "https://www.example.org/favicon.ico",
        ]

        status, result = self.call({
            "events": [event(url=url) for url in excluded]
            + [event(url="https://www.example.org/news/report.pdf?x=.css")]
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["skipped"], len(excluded))
        self.assertEqual(
            {request["url"] for request in self.matomo.tracked},
            {"https://www.example.org/news/report.pdf?x=.css"},
        )

    def test_excluded_urls_can_be_configured(self):
        api.portal.set_registry_record(
            "matomoaitracker.matomo_excluded_urls", ["^/private/", "[invalid"]
        )

        self.call({
            "events": [
                event(url="https://www.example.org/private/page"),
                event(url="https://www.example.org/style.css"),
            ]
        })

        self.assertEqual(
            [request["url"] for request in self.matomo.tracked],
            ["https://www.example.org/style.css"],
        )

    def test_documents_are_tracked_as_downloads(self):
        self.configure_bot_site()
        url = "https://www.example.org/report/@@download/file"

        self.call({"events": [event(url=url, content_type="application/pdf")]})

        for request in self.matomo.tracked:
            self.assertEqual(request["download"], url)
            self.assertEqual(request["url"], url)

    def test_pages_are_not_downloads(self):
        for content_type, status in (
            ("text/html; charset=utf-8", 200),
            ("application/json", 200),
            ("application/xhtml+xml", 200),
            ("application/pdf", 404),
            ("", 200),
        ):
            with self.subTest(content_type=content_type, status=status):
                self.matomo.bulk_requests.clear()

                self.call({"events": [event(content_type=content_type, status=status)]})

                self.assertNotIn("download", self.matomo.tracked[0])

    def test_switched_off(self):
        self.configure_bot_site()
        api.portal.set_registry_record("matomoaitracker.matomo_tracking_enabled", False)

        status, result = self.call({"events": [event(), event()]})

        # Dropped: the shipper does not send them again.
        self.assertEqual(status, 200)
        self.assertEqual(
            result, {"tracked": 0, "rejected": 0, "skipped": 2, "disabled": True}
        )
        self.assertEqual(self.matomo.bulk_requests, [])

    def test_categories_tracked_in_bot_site(self):
        self.configure_bot_site()
        api.portal.set_registry_record(
            "matomoaitracker.matomo_bot_site_categories", ["search"]
        )

        status, result = self.call({
            "events": [
                event(),
                event(user_agent="OAI-SearchBot/1.0"),
                event(user_agent="GPTBot/1.1"),
            ]
        })

        self.assertEqual(status, 200)
        self.assertEqual(result, {"tracked": 2, "rejected": 0, "skipped": 1})
        self.assertEqual(
            [(r["idsite"], r["ua"]) for r in self.matomo.tracked],
            [
                ("1", "Mozilla/5.0 (compatible; Claude-User/1.0)"),
                ("2", "OAI-SearchBot/1.0"),
            ],
        )

    def test_status_counts_batches(self):
        self.call({"events": [event(), event(user_agent="Firefox")]})
        self.call({"events": [event()]})

        self.assertEqual(STATUS.batches, 2)
        self.assertEqual(STATUS.tracked, 2)
        self.assertEqual(STATUS.skipped, 1)
        self.assertIsNotNone(STATUS.last_batch)
        self.assertIsNone(STATUS.last_error)

    def test_status_keeps_the_last_error(self):
        self.matomo.status = 500

        self.call({"events": [event()]})

        self.assertEqual(STATUS.batches, 0)
        self.assertIn("HTTP 500", STATUS.last_error or "")

        with patch.dict(os.environ, clear=True):
            self.call({"events": [event()]})
        self.assertIn("No Matomo token", STATUS.last_error or "")

    def test_token_from_the_control_panel(self):
        api.portal.set_registry_record("matomoaitracker.matomo_token_auth", "stored")

        with patch.dict(os.environ, clear=True):
            status, _result = self.call({"events": [event()]})

        self.assertEqual(status, 200)
        self.assertEqual(self.matomo.bulk_requests[0]["token_auth"], "stored")

    def test_environment_overrides_the_stored_token(self):
        api.portal.set_registry_record("matomoaitracker.matomo_token_auth", "stored")

        self.call({"events": [event()]})

        self.assertEqual(self.matomo.bulk_requests[0]["token_auth"], "secret")

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
        self.portal = cast(Any, self.layer["portal"])
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
