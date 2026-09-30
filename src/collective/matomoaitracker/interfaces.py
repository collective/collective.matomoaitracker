from collective.matomoaitracker import _
from zope import schema
from zope.interface import Interface
from zope.publisher.interfaces.browser import IDefaultBrowserLayer


class IBrowserLayer(IDefaultBrowserLayer):
    """Marker interface that defines a browser layer."""


class IMatomoAITrackingControlPanel(Interface):
    """Settings for Matomo AI Tracking."""

    matomo_site_id = schema.Int(
        title=_("Matomo Site ID"),
        description=_("The ID of the site in Matomo for tracking."),
        min=1,
    )

    matomo_base_url = schema.TextLine(
        title=_("Matomo Base URL"),
        description=_("The base URL of the Matomo instance."),
        default="",
    )
