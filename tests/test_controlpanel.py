from collective.matomoaitracker.testing import FUNCTIONAL_TESTING
from plone.app.testing import SITE_OWNER_NAME
from plone.app.testing import SITE_OWNER_PASSWORD
from plone.registry.interfaces import IRegistry
from plone.testing.zope import Browser
from typing import Any
from typing import cast
from unittest import TestCase
from zope.component import getUtility


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
