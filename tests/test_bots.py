from collective.matomoaitracker.bots import BOTS
from collective.matomoaitracker.bots import CATEGORIES
from collective.matomoaitracker.bots import classify
from pathlib import Path

import pytest
import re


VCL = Path(__file__).parent.parent / "varnish" / "matomoaitracker.vcl"


def vcl_bots():
    """Return the bot names per category, in the order the VCL checks them."""
    pattern = re.compile(
        r'User-Agent ~ "\(\?i\)\(([^)]*)\)"\)\s*\{\s*'
        r'set req\.http\.X-AI-Bot = "(\w+)";'
    )
    return [
        (category, tuple(names.split("|")))
        for names, category in pattern.findall(VCL.read_text())
    ]


def test_vcl_has_the_same_bots_as_python():
    assert vcl_bots() == [(category, BOTS[category]) for category in CATEGORIES]


@pytest.mark.parametrize(
    "user_agent,expected",
    [
        ("Mozilla/5.0 (compatible; Claude-User/1.0)", ("Claude-User", "user")),
        ("claude-searchbot/1.0", ("Claude-SearchBot", "search")),
        ("Mozilla/5.0 (compatible; ClaudeBot/1.0)", ("ClaudeBot", "training")),
        ("GPTBot/1.1", ("GPTBot", "training")),
        # Categories are checked in order, like the VCL does.
        ("OAI-SearchBot GPTBot", ("OAI-SearchBot", "search")),
        ("Mozilla/5.0 Firefox/140.0", None),
        ("", None),
        (None, None),
    ],
)
def test_classify(user_agent, expected):
    assert classify(user_agent) == expected
