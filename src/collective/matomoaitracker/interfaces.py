from collective.matomoaitracker import _
from zope import schema
from zope.interface import Interface
from zope.publisher.interfaces.browser import IDefaultBrowserLayer


class IBrowserLayer(IDefaultBrowserLayer):
    """Marker interface that defines a browser layer."""


class IMatomoAITrackingControlPanel(Interface):
    """Settings for Matomo AI Tracking.

    The Matomo token_auth is not stored here but read from the
    MATOMO_AI_TOKEN_AUTH environment variable, so it does not end up in the
    database and is not visible to site administrators.
    """

    matomo_site_id = schema.Int(
        title=_("Matomo Site ID"),
        description=_(
            "The ID of the site in Matomo. AI assistants fetching pages for a "
            "user are tracked in its AI Chatbots report."
        ),
        min=1,
    )

    matomo_base_url = schema.TextLine(
        title=_("Matomo Base URL"),
        description=_("The base URL of the Matomo instance."),
        default="",
    )

    matomo_bot_site_id = schema.Int(
        title=_("Matomo AI bots Site ID"),
        description=_(
            "Optional ID of a separate Matomo site in which every AI bot "
            "request, including search and training crawlers, is tracked as a "
            "visit. Leave empty to only track AI assistants."
        ),
        min=1,
        required=False,
    )

    matomo_dimension_category = schema.Int(
        title=_("Bot category dimension ID"),
        description=_(
            "Optional ID of the custom dimension in the AI bots site that "
            "receives the bot category: user, search or training."
        ),
        min=1,
        required=False,
    )

    matomo_dimension_cache = schema.Int(
        title=_("Cache status dimension ID"),
        description=_(
            "Optional ID of the custom dimension in the AI bots site that "
            "receives how Varnish handled the request: hit, miss or pass."
        ),
        min=1,
        required=False,
    )
