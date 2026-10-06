from collective.matomoaitracker.status import STATUS
from collective.matomoaitracker.testing import FUNCTIONAL_TESTING
from fake_matomo import FakeMatomo
from plone import api
from plone.app.testing import SITE_OWNER_NAME
from plone.app.testing import SITE_OWNER_PASSWORD
from plone.registry.interfaces import IRegistry
from plone.testing.zope import Browser
from typing import Any
from typing import cast
from unittest import TestCase
from unittest.mock import patch
from zope.component import getUtility

import os
import transaction


class ControlPanelTestCase(TestCase):
    """Test the addon's control panel using the functional Plone layer."""

    layer = FUNCTIONAL_TESTING

    def setUp(self):
        portal = cast(Any, self.layer["portal"])
        self.portal_url = portal.absolute_url()
        self.browser = Browser(self.layer["app"])
        self.browser.handleErrors = False
        self.browser.addHeader(
            "Authorization", "Basic " + SITE_OWNER_NAME + ":" + SITE_OWNER_PASSWORD
        )

    def test_control_panel_link_to_overview(self):
        self.browser.open(self.portal_url + "/@@overview-controlpanel")
        link = self.browser.getLink("Matomo AI Chatbot Tracking")
        self.assertEqual(link.url, self.portal_url + "/@@matomo-ai-controlpanel")

    def test_control_panel_contents(self):
        self.browser.open(self.portal_url + "/@@matomo-ai-controlpanel")
        self.assertIn("Matomo Settings", self.browser.contents or "")

    def test_control_panel_sidebar(self):
        self.browser.open(self.portal_url + "/@@matomo-ai-controlpanel")
        self.assertIn("General", self.browser.contents or "")
        link = self.browser.getLink("Add-ons")
        self.assertEqual(link.url, self.portal_url + "/prefs_install_products_form")


class ControlPanelFunctionalTestCase(TestCase):
    """Test saving the addon's Matomo settings."""

    layer = FUNCTIONAL_TESTING

    def setUp(self):
        portal = cast(Any, self.layer["portal"])
        self.portal_url = portal.absolute_url()
        self.browser = Browser(self.layer["app"])
        self.browser.handleErrors = False
        self.browser.addHeader(
            "Authorization", "Basic " + SITE_OWNER_NAME + ":" + SITE_OWNER_PASSWORD
        )

    def test_matomo_settings_saved(self):
        self.browser.open(self.portal_url + "/@@matomo-ai-controlpanel")
        site_id = self.browser.getControl(label="Matomo Site ID")
        site_id.value = "42"
        base_url = self.browser.getControl(label="Matomo Base URL")
        base_url.value = "https://matomo.example"
        self.browser.getControl("Save").click()
        registry = getUtility(IRegistry)
        self.assertEqual(registry.records["matomoaitracker.matomo_site_id"].value, 42)
        self.assertEqual(
            registry.records["matomoaitracker.matomo_base_url"].value,
            "https://matomo.example",
        )


class ControlPanelStatusTestCase(TestCase):
    """The tracking status, the categories and the connection test."""

    layer = FUNCTIONAL_TESTING

    def setUp(self):
        portal = cast(Any, self.layer["portal"])
        self.portal_url = portal.absolute_url()
        self.matomo = FakeMatomo()
        self.addCleanup(self.matomo.stop)
        for name, value in (
            ("matomo_base_url", self.matomo.url),
            ("matomo_site_id", 1),
            ("matomo_bot_site_id", 2),
            ("matomo_dimension_category", 3),
            ("matomo_dimension_cache", 4),
            ("matomo_dimension_bot", 5),
        ):
            api.portal.set_registry_record(f"matomoaitracker.{name}", value)
        transaction.commit()
        environment = patch.dict(os.environ, {"MATOMO_AI_TOKEN_AUTH": "secret"})
        environment.start()
        self.addCleanup(environment.stop)
        STATUS.reset()
        self.browser = Browser(self.layer["app"])
        self.browser.handleErrors = False
        self.browser.addHeader(
            "Authorization", "Basic " + SITE_OWNER_NAME + ":" + SITE_OWNER_PASSWORD
        )

    def open(self):
        self.browser.open(self.portal_url + "/@@matomo-ai-controlpanel")
        return self.browser.contents or ""

    def test_status_before_any_batch(self):
        contents = self.open()

        self.assertIn("Tracking status", contents)
        self.assertIn("None yet: is the shipper running?", contents)

    def test_status_after_batches(self):
        STATUS.record_batch(tracked=5, rejected=1, skipped=2)
        STATUS.record_error("Matomo did not accept the requests: HTTP 500")

        contents = self.open()

        self.assertNotIn("None yet", contents)
        # Formatted in the browser by Plone's pat-display-time.
        assert STATUS.last_batch is not None
        self.assertIn(f'datetime="{STATUS.last_batch.isoformat()}"', contents)
        self.assertIn('data-pat-display-time="from-now: true"', contents)
        self.assertIn("Matomo did not accept the requests: HTTP 500", contents)

    def test_categories_are_checkboxes(self):
        self.open()

        for label in (
            "AI assistants fetching a page for a user",
            "AI search crawlers",
            "AI training crawlers",
        ):
            self.assertTrue(self.browser.getControl(label).selected)

    def test_connection(self):
        self.open()

        self.browser.getControl("Test connection").click()

        contents = self.browser.contents or ""
        self.assertIn("Matomo Site ID 1: Site 1", contents)
        self.assertIn("AI bots Site ID 2: Site 2", contents)
        self.assertIn("Bot category dimension 3: Bot category (visit scope)", contents)
        self.assertIn("Cache status dimension 4: not active", contents)
        self.assertIn("Bot name dimension 5: Bot name (action scope)", contents)
        self.assertEqual(
            {call["token_auth"] for call in self.matomo.api_calls}, {"secret"}
        )

    def test_connection_problems(self):
        api.portal.set_registry_record("matomoaitracker.matomo_bot_site_id", 9)
        transaction.commit()
        self.open()

        self.browser.getControl("Test connection").click()

        contents = self.browser.contents or ""
        self.assertIn("AI bots Site ID 9: The site id 9 is invalid", contents)
        self.assertIn("Custom dimensions of the AI bots site", contents)

        with patch.dict(os.environ, clear=True):
            self.open()
            self.browser.getControl("Test connection").click()
        self.assertIn(
            "No Matomo token: paste one in the control panel",
            self.browser.contents or "",
        )

        self.matomo.stop()
        self.open()
        self.browser.getControl("Test connection").click()
        self.assertIn("Cannot reach Matomo", self.browser.contents or "")


class ControlPanelTokenTestCase(TestCase):
    """Pasting a Matomo token in the control panel."""

    layer = FUNCTIONAL_TESTING

    def setUp(self):
        portal = cast(Any, self.layer["portal"])
        self.portal_url = portal.absolute_url()
        api.portal.set_registry_record("matomoaitracker.matomo_site_id", 1)
        api.portal.set_registry_record(
            "matomoaitracker.matomo_base_url", "https://matomo.example"
        )
        transaction.commit()
        environment = patch.dict(os.environ, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.browser = Browser(self.layer["app"])
        self.browser.handleErrors = False
        self.browser.addHeader(
            "Authorization", "Basic " + SITE_OWNER_NAME + ":" + SITE_OWNER_PASSWORD
        )

    def open(self):
        self.browser.open(self.portal_url + "/@@matomo-ai-controlpanel")

    def token(self):
        return api.portal.get_registry_record("matomoaitracker.matomo_token_auth")

    def save(self, token=""):
        self.open()
        self.browser.getControl(label="Matomo token").value = token
        self.browser.getControl("Save").click()

    def test_paste_a_token(self):
        self.open()
        self.assertIn('placeholder="No token stored"', self.browser.contents or "")

        self.save("pasted-token")

        self.assertEqual(self.token(), "pasted-token")
        self.open()
        contents = self.browser.contents or ""
        self.assertNotIn("pasted-token", contents)
        self.assertIn('placeholder="A token is stored"', contents)

    def test_saving_other_settings_keeps_the_token(self):
        self.save("pasted-token")

        self.open()
        self.browser.getControl(label="Matomo Site ID").value = "7"
        self.browser.getControl("Save").click()

        self.assertEqual(self.token(), "pasted-token")
        self.assertEqual(
            api.portal.get_registry_record("matomoaitracker.matomo_site_id"), 7
        )

    def test_remove_the_token(self):
        self.open()
        with self.assertRaises(LookupError):
            self.browser.getControl("Remove token")
        self.save("pasted-token")

        self.open()
        self.browser.getControl("Remove token").click()

        self.assertEqual(self.token(), "")
        self.assertIn("The Matomo token is removed.", self.browser.contents or "")

    def test_environment_variable_overrides(self):
        with patch.dict(os.environ, {"MATOMO_AI_TOKEN_AUTH": "from-env"}):
            self.open()

        self.assertIn(
            'placeholder="Set by the MATOMO_AI_TOKEN_AUTH environment variable"',
            self.browser.contents or "",
        )

    def test_tracking_switched_by_environment(self):
        api.portal.set_registry_record("matomoaitracker.matomo_tracking_enabled", True)
        transaction.commit()

        with patch.dict(os.environ, {"MATOMO_AI_TRACKING_ENABLED": "false"}):
            self.open()
            contents = self.browser.contents or ""
            checkbox = self.browser.getControl(label="Track AI bots")
            self.assertFalse(checkbox.selected)
            self.assertTrue(checkbox.disabled)
            self.assertIn(
                "Set by the MATOMO_AI_TRACKING_ENABLED environment variable", contents
            )

            self.browser.getControl(label="Matomo Site ID").value = "7"
            self.browser.getControl("Save").click()

        # The stored setting is kept, for when the variable is removed.
        self.assertTrue(
            api.portal.get_registry_record("matomoaitracker.matomo_tracking_enabled")
        )
        self.assertEqual(
            api.portal.get_registry_record("matomoaitracker.matomo_site_id"), 7
        )

    def test_tracking_switch_without_environment(self):
        self.open()

        checkbox = self.browser.getControl(label="Track AI bots")
        self.assertFalse(checkbox.disabled)
        self.assertNotIn("MATOMO_AI_TRACKING_ENABLED", self.browser.contents or "")
