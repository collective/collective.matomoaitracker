from collective.matomoaitracker import PACKAGE_NAME
from plone import api
from plone.registry.interfaces import IRegistry
from zope.component import getUtility


PROFILE = f"{PACKAGE_NAME}:default"
NEW_RECORDS = (
    "matomoaitracker.matomo_bot_site_id",
    "matomoaitracker.matomo_dimension_category",
    "matomoaitracker.matomo_dimension_cache",
)


def test_upgrade_1000_to_1001(portal):
    """A site installed with 1000 gets the new settings and role."""
    registry = getUtility(IRegistry)
    for name in NEW_RECORDS:
        del registry.records[name]
    api.portal.set_registry_record("matomoaitracker.matomo_site_id", 7)
    portal.manage_permission(
        "collective.matomoaitracker: Submit tracking events", ["Manager"]
    )
    setup = portal.portal_setup
    setup.setLastVersionForProfile(PROFILE, "1000")

    setup.upgradeProfile(PROFILE)

    assert setup.getLastVersionForProfile(PROFILE) == ("1001",)
    for name in NEW_RECORDS:
        assert name in registry.records
    assert api.portal.get_registry_record("matomoaitracker.matomo_site_id") == 7
    assert "Matomo AI Tracker" in {
        role["name"]
        for role in portal.rolesOfPermission(
            "collective.matomoaitracker: Submit tracking events"
        )
        if role["selected"]
    }
