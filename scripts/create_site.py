from AccessControl.SecurityManagement import newSecurityManager
from collective.matomoaitracker.interfaces import IBrowserLayer
from plone.base.utils import get_installer
from Products.CMFPlone.factory import _DEFAULT_PROFILE
from Products.CMFPlone.factory import addPloneSite
from Products.GenericSetup.tool import SetupTool
from Testing.makerequest import makerequest
from zope.component.hooks import setSite
from zope.interface import directlyProvidedBy
from zope.interface import directlyProvides

import os
import transaction


truthy = frozenset(("t", "true", "y", "yes", "on", "1"))


def asbool(s):
    """Return the boolean value ``True`` if the case-lowered value of string
    input ``s`` is a :term:`truthy string`. If ``s`` is already one of the
    boolean values ``True`` or ``False``, return it."""
    if s is None:
        return False
    if isinstance(s, bool):
        return s
    s = str(s).strip()
    return s.lower() in truthy


DELETE_EXISTING = asbool(os.getenv("DELETE_EXISTING"))

app = makerequest(globals()["app"])

request = app.REQUEST

ifaces = [IBrowserLayer]
for iface in directlyProvidedBy(request):
    ifaces.append(iface)

directlyProvides(request, *ifaces)

admin = app.acl_users.getUserById("admin")
admin = admin.__of__(app.acl_users)
newSecurityManager(None, admin)

site_id = "Plone"
payload = {
    "title": "Collective Matomo AI Tracking",
    "profile_id": _DEFAULT_PROFILE,
    "distribution_name": "classic",
    "setup_content": False,
    "default_language": "en",
    "portal_timezone": "UTC",
}

if site_id in app.objectIds() and DELETE_EXISTING:
    app.manage_delObjects([site_id])
    transaction.commit()
    app._p_jar.sync()

if site_id not in app.objectIds():
    site = addPloneSite(app, site_id, **payload)
    transaction.commit()

    portal_setup: SetupTool = site.portal_setup
    portal_setup.runAllImportStepsFromProfile(
        "profile-collective.matomoaitracker:default"
    )
    transaction.commit()

site = app[site_id]
# Import steps look up the registry of the active site.
setSite(site)

# Bring an existing site up to date with the add-on's profile.  The settings
# and roles are imported again as well: that adds what is missing and keeps
# existing values, also when the installed profile version is not recorded.
site.portal_setup.upgradeProfile("collective.matomoaitracker:default")
for step in ("plone.app.registry", "rolemap"):
    site.portal_setup.runImportStepFromProfile(
        "profile-collective.matomoaitracker:default", step, run_dependencies=False
    )
transaction.commit()

SETTINGS = {
    "MATOMO_BASE_URL": ("matomo_base_url", str),
    "MATOMO_SITE_ID": ("matomo_site_id", int),
    "MATOMO_BOT_SITE_ID": ("matomo_bot_site_id", int),
    "MATOMO_DIMENSION_CATEGORY": ("matomo_dimension_category", int),
    "MATOMO_DIMENSION_CACHE": ("matomo_dimension_cache", int),
    "MATOMO_DIMENSION_BOT": ("matomo_dimension_bot", int),
}
registry = site.portal_registry
for variable, (record, convert) in SETTINGS.items():
    value = os.getenv(variable)
    if value:
        registry[f"matomoaitracker.{record}"] = convert(value)
transaction.commit()

# Purge Varnish when content changes, see varnish/default.vcl.
CACHING_PROXIES = os.getenv("CACHING_PROXIES")
if CACHING_PROXIES:
    installer = get_installer(site)
    if not installer.is_product_installed("plone.app.caching"):
        installer.install_product("plone.app.caching")
    site.portal_setup.upgradeProfile("plone.app.caching:default")
    prefix = "plone.cachepurging.interfaces.ICachePurgingSettings"
    registry[f"{prefix}.enabled"] = True
    registry[f"{prefix}.cachingProxies"] = tuple(CACHING_PROXIES.split())
    transaction.commit()

# Service user for the shipper, see shipper/matomo_ai_shipper.py.
SHIPPER_USERNAME = os.getenv("MATOMO_AI_USERNAME")
SHIPPER_PASSWORD = os.getenv("MATOMO_AI_PASSWORD")
if SHIPPER_USERNAME and SHIPPER_PASSWORD:
    users = site.acl_users
    if users.getUserById(SHIPPER_USERNAME) is None:
        users.userFolderAddUser(
            SHIPPER_USERNAME, SHIPPER_PASSWORD, ["Matomo AI Tracker"], []
        )
    else:
        users.userFolderEditUser(
            SHIPPER_USERNAME, SHIPPER_PASSWORD, ["Matomo AI Tracker"], []
        )
    transaction.commit()
