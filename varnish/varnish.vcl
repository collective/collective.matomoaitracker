# Insert into the generated VCL's vcl_deliver subroutine.
# Add `import curl;` at the top level of the generated VCL.
if (
    req.http.User-Agent ~ "(?i)(ChatGPT-User|GPTBot|OAI-SearchBot|Claude-User|ClaudeBot|Claude-SearchBot|Perplexity-User|PerplexityBot|DeepSeekBot|Bytespider|Amazonbot|Applebot-Extended|Meta-ExternalAgent|cohere-ai|YouBot|AI2Bot|Diffbot)"
    && req.http.X-Forwarded-Proto ~ "(?i)^https?$"
    && std.getenv("MATOMO_AI_PLONE_ORIGIN") ~ "^http://[^/]+$"
) {
    curl.set_connect_timeout(250);
    curl.set_timeout(1000);
    curl.header_add("User-Agent: " + req.http.User-Agent);
    curl.get(
        std.getenv("MATOMO_AI_PLONE_ORIGIN")
        + "/@@matomoaitracker?url="
        + curl.escape(
            req.http.X-Forwarded-Proto + "://" + req.http.host + req.url
        )
    );
    curl.free();
}