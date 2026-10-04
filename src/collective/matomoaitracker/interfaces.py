from collective.matomoaitracker import _
from collective.matomoaitracker.bots import SEARCH
from collective.matomoaitracker.bots import TRAINING
from collective.matomoaitracker.bots import USER
from zope import schema
from zope.interface import Interface
from zope.interface import Invalid
from zope.interface import provider
from zope.publisher.interfaces.browser import IDefaultBrowserLayer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary

import re


# Requests for these URL paths are not pages or documents, but resources of
# pages, like Matomo's own trackers skip them.
DEFAULT_EXCLUDED_URLS = [
    r"/\+\+(resource|plone|theme)\+\+",
    r"/@@images(/|$)",
    r"\.(css|js|mjs|map|json|webmanifest|wasm|xml|rss|atom|txt)$",
    r"\.(png|jpe?g|gif|webp|avif|svg|ico|bmp|tiff?)$",
    r"\.(woff2?|ttf|otf|eot)$",
]


@provider(IVocabularyFactory)
def bot_categories(context):
    """Named vocabulary: registry records cannot store inline vocabularies."""
    return SimpleVocabulary([
        SimpleTerm(USER, title=_("AI assistants fetching a page for a user")),
        SimpleTerm(SEARCH, title=_("AI search crawlers")),
        SimpleTerm(TRAINING, title=_("AI training crawlers")),
    ])


def valid_pattern(value):
    try:
        re.compile(value)
    except re.error as error:
        raise Invalid(
            _(
                "Invalid regular expression ${pattern}: ${error}",
                mapping={"pattern": value, "error": str(error)},
            )
        ) from error
    return True


class IBrowserLayer(IDefaultBrowserLayer):  # pyright: ignore[reportGeneralTypeIssues]
    """Marker interface that defines a browser layer."""


class IMatomoAITrackingControlPanel(Interface):  # pyright: ignore[reportGeneralTypeIssues]
    """Settings for Matomo AI Tracking.

    The MATOMO_AI_TOKEN_AUTH environment variable overrides the stored Matomo
    token, for hosting setups that keep secrets out of the database.
    """

    matomo_tracking_enabled = schema.Bool(
        title=_("Track AI bots"),
        description=_(
            "When switched off, AI bot requests are dropped instead of sent to "
            "Matomo. They are not tracked later when switching it on again."
        ),
        default=True,
        required=False,
    )

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

    matomo_token_auth = schema.Password(
        title=_("Matomo token"),
        description=_(
            "An auth token of a Matomo user with write access to the sites, "
            "created in Matomo under Personal, Security. Matomo needs it for "
            "the time and client IP of the requests. The stored token is not "
            "shown: leave the field empty to keep it."
        ),
        default="",
        required=False,
    )

    matomo_bot_site_id = schema.Int(
        title=_("Matomo AI bots Site ID"),
        description=_(
            "Optional ID of a separate Matomo site in which every AI bot "
            "request, including search and training crawlers, is tracked. "
            "Matomo's AI Assistants reports leave crawlers out, this site shows "
            "how many requests they make, when, and how they load the server. "
            "It is separate, as crawler requests count as visits and would "
            "otherwise mix with human visitors. Leave empty to only track AI "
            "assistants."
        ),
        min=1,
        required=False,
    )

    matomo_bot_site_categories = schema.List(
        title=_("Categories tracked in the AI bots site"),
        description=_(
            "Which AI bots are tracked in the AI bots site. AI assistants are "
            "always tracked in the AI Chatbots report of the Matomo site."
        ),
        value_type=schema.Choice(  # pyright: ignore[reportArgumentType]
            vocabulary="collective.matomoaitracker.BotCategories"
        ),
        default=[USER, SEARCH, TRAINING],
        missing_value=[],
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

    matomo_dimension_bot = schema.Int(
        title=_("Bot name dimension ID"),
        description=_(
            "Optional ID of the custom dimension in the AI bots site that "
            "receives the name of the bot, like GPTBot or ClaudeBot."
        ),
        min=1,
        required=False,
    )

    matomo_excluded_urls = schema.List(
        title=_("Excluded URLs"),
        description=_(
            "Requests for URL paths matching one of these regular expressions "
            "are not tracked, like images, styles and scripts of pages. One "
            "expression per line, matched case-insensitively against the path."
        ),
        value_type=schema.TextLine(  # pyright: ignore[reportArgumentType]
            constraint=valid_pattern
        ),
        default=DEFAULT_EXCLUDED_URLS,
        missing_value=[],
        required=False,
    )
