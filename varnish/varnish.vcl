if (req.http.User-Agent ~ "(?i)(ChatGPT-User|GPTBot|OAI-SearchBot|Claude-User|ClaudeBot|Claude-SearchBot|Perplexity-User|PerplexityBot|DeepSeekBot|Bytespider|Amazonbot|Applebot-Extended|Meta-ExternalAgent|cohere-ai|YouBot|AI2Bot|Diffbot)") {
    std.log("MATOMO_AI_TRACK " + req.http.User-Agent);
}