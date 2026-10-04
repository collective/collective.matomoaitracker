"""Known AI bots and their category.

``varnish/varnish.vcl`` classifies requests with the same lists; a test checks
that both stay in sync.
"""

# Fetches a page on behalf of a user asking an AI assistant something.
USER = "user"
# Crawls for an AI search index.
SEARCH = "search"
# Crawls for training data.
TRAINING = "training"

CATEGORIES = (USER, SEARCH, TRAINING)

BOTS = {
    USER: (
        "Claude-User",
        "ChatGPT-User",
        "Perplexity-User",
        "MistralAI-User",
        "Gemini-Deep-Research",
        "Google-NotebookLM",
        # Former name of Google-NotebookLM.
        "Google-GeminiNotebook",
    ),
    SEARCH: (
        "Claude-SearchBot",
        "OAI-SearchBot",
        "PerplexityBot",
        "YouBot",
    ),
    TRAINING: (
        "ClaudeBot",
        "GPTBot",
        "CCBot",
        "Meta-ExternalAgent",
        "Bytespider",
        "Amazonbot",
        "DeepSeekBot",
        "cohere-ai",
        "AI2Bot",
        "Diffbot",
    ),
}


def classify(user_agent):
    """Return ``(bot_name, category)`` for a User-Agent, or ``None``.

    Categories are checked in the order of ``CATEGORIES``, like the VCL does.
    """
    if not user_agent:
        return None
    lowered = user_agent.lower()
    for category in CATEGORIES:
        for name in BOTS[category]:
            if name.lower() in lowered:
                return name, category
    return None
