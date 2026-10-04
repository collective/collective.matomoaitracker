# Classify AI bot requests for collective.matomoaitracker.
#
# Include this file at the top level of your VCL, after `import std;` and
# before your own subroutines:
#
#     include "matomoaitracker.vcl";
#
# Varnish concatenates subroutines that are defined more than once, so the
# code below runs at the start of your own vcl_recv and vcl_backend_fetch.
#
# Nothing here makes HTTP calls: the category is written to the Varnish log as
# `ai-bot:<category>`, where varnishncsa picks it up (see varnishncsa/).
# The bot lists must match src/collective/matomoaitracker/bots.py.

sub vcl_recv {
    # Never trust a classification sent by the client.
    unset req.http.X-AI-Bot;

    if (req.http.User-Agent ~ "(?i)(Claude-User|ChatGPT-User|Perplexity-User|MistralAI-User|Gemini-Deep-Research|Google-NotebookLM|Google-GeminiNotebook)") {
        set req.http.X-AI-Bot = "user";
    } elsif (req.http.User-Agent ~ "(?i)(Claude-SearchBot|OAI-SearchBot|PerplexityBot|YouBot)") {
        set req.http.X-AI-Bot = "search";
    } elsif (req.http.User-Agent ~ "(?i)(ClaudeBot|GPTBot|CCBot|Meta-ExternalAgent|Bytespider|Amazonbot|DeepSeekBot|cohere-ai|AI2Bot|Diffbot)") {
        set req.http.X-AI-Bot = "training";
    }

    if (req.http.X-AI-Bot) {
        # Log records cannot be forged by clients, unlike request headers.
        std.log("ai-bot:" + req.http.X-AI-Bot);
    }

    # The tracking endpoint is only for the shipper, which calls Plone directly.
    if (req.url ~ "(?i)/@@matomoaitracker") {
        return (synth(404));
    }
}

sub vcl_backend_fetch {
    # The classification is only for the Varnish log, not for the backend.
    unset bereq.http.X-AI-Bot;
}
