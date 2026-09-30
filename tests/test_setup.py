"""Setup tests for this package."""

from collective.matomoaitracker import PACKAGE_NAME

import pytest


class TestSetup:
    def test_addon_installed(self, installer):
        """Test if collective.matomoaitracker is installed."""
        assert installer.is_product_installed(PACKAGE_NAME) is True

    def test_browserlayer(self, browser_layers):
        """Test that IBrowserLayer is registered."""
        from collective.matomoaitracker.interfaces import IBrowserLayer

        assert IBrowserLayer in browser_layers

    def test_latest_version(self, profile_last_version):
        """Test latest version of default profile."""
        assert profile_last_version(f"{PACKAGE_NAME}:default") == "1000"


class TestSetupUninstall:
    @pytest.fixture(autouse=True)
    def uninstalled(self, installer):
        installer.uninstall_product(PACKAGE_NAME)

    def test_addon_uninstalled(self, installer):
        """Test if collective.matomoaitracker is cleanly uninstalled."""
        assert installer.is_product_installed(PACKAGE_NAME) is False

    def test_browserlayer_not_registered(self, browser_layers):
        """Test that IBrowserLayer is removed."""
        from collective.matomoaitracker.interfaces import IBrowserLayer

        assert IBrowserLayer not in browser_layers
