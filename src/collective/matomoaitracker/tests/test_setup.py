"""Setup tests for this package."""

from collective.matomoaitracker.testing import INTEGRATION_TESTING
from plone.base.utils import get_installer

import unittest


class TestSetup(unittest.TestCase):
    """Test that collective.matomoaitracker is properly installed."""

    layer = INTEGRATION_TESTING

    def setUp(self):
        """Custom shared utility setup for tests."""
        self.portal = self.layer["portal"]
        self.installer = get_installer(self.portal)

    def test_product_installed(self):
        """Test if collective.matomoaitracker is installed."""
        self.assertTrue(self.installer.is_product_installed("collective.matomoaitracker"))

    def test_browserlayer(self):
        """Test that IBrowserLayer is registered."""
        from collective.matomoaitracker.interfaces import IBrowserLayer
        from plone.browserlayer import utils

        self.assertIn(IBrowserLayer, utils.registered_layers())


class TestUninstall(unittest.TestCase):

    layer = INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        self.installer = get_installer(self.portal)
        self.installer.uninstall_product("collective.matomoaitracker")

    def test_product_uninstalled(self):
        """Test if collective.matomoaitracker is cleanly uninstalled."""
        self.assertFalse(self.installer.is_product_installed("collective.matomoaitracker"))

    def test_browserlayer_removed(self):
        """Test that IBrowserLayer is removed."""
        from collective.matomoaitracker.interfaces import IBrowserLayer
        from plone.browserlayer import utils

        self.assertNotIn(IBrowserLayer, utils.registered_layers())
