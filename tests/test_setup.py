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

    def test_tracking_permission_roles(self, portal):
        """Only managers and the shipper's role may submit tracking events."""
        roles = {
            role["name"]
            for role in portal.rolesOfPermission(
                "collective.matomoaitracker: Submit tracking events"
            )
            if role["selected"]
        }
        assert roles == {"Manager", "Site Administrator", "Matomo AI Tracker"}

    def test_latest_version(self, profile_last_version):
        """Test latest version of default profile."""
        assert profile_last_version(f"{PACKAGE_NAME}:default") == "1001"


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
