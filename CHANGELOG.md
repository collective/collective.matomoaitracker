# Changelog

<!--
   You should *NOT* be adding new change log entries to this file.
   You should create a file in the news directory instead.
   For helpful instructions, please see:
   https://github.com/plone/plone.releaser/blob/master/ADD-A-NEWS-ITEM.rst
-->

<!-- towncrier release notes start -->

## 1.0.0a1 (2026-10-08)


### Breaking

- Track AI bots from the Varnish log instead of with a synchronous libvmod-curl call, so bots are no longer slowed down and cache hits are tracked without any HTTP call. Varnish classifies bots as user, search or training and logs that, varnishncsa writes the requests to a file, and a new shipper (`shipper/matomo_ai_shipper.py`) sends them in batches to `@@matomoaitracker`, which forwards them to Matomo's bulk tracking API with the original request time. AI assistants go to Matomo's AI Chatbots report; optionally all AI bots go to a separate Matomo site with the bot category and cache status as custom dimensions. Outages of Plone or Matomo delay tracking instead of losing it.

  `@@matomoaitracker` now only accepts POSTed JSON batches from users with the new `collective.matomoaitracker: Submit tracking events` permission (role "Matomo AI Tracker"), and needs the Matomo token in the `MATOMO_AI_TOKEN_AUTH` environment variable. `varnish/varnish.vcl` is replaced by `varnish/matomoaitracker.vcl`, which is included at the top level of the VCL. 


### Feature

- Add a Docker stack for development: Varnish in front of Nginx doing the VirtualHostMonster rewrites to Plone, with varnishncsa, the shipper and a fake Matomo for the tracking. `make install` builds the images, `make stack-start` runs them, `make varnish-test` and `make stack-test` test them. Settings can be put in a `.env` file, see `.env.example`. Varnish uses the configuration of Plone's cookieplone templates. 
- Add an optional "Bot name" custom dimension to the AI bots site, with the name of the bot like GPTBot or ClaudeBot, to see which crawlers cause load peaks. 
- Add the Gemini-Deep-Research and Google-NotebookLM AI assistants, skip the resources of pages (configurable as "Excluded URLs" in the control panel), track documents like PDFs as downloads based on their content type, and send `source=Varnish` with requests for the AI Chatbots report. 
- Give site administrators more control in the control panel: switch AI bot tracking off, choose which bot categories are tracked in the AI bots site, check the settings against Matomo with "Test connection", and see when the shipper last delivered, how many requests were tracked, and the last error. 
- The Matomo token can be pasted in the control panel. It is never sent back to the browser, saving the form with an empty token field keeps it, and "Remove token" removes it. The `MATOMO_AI_TOKEN_AUTH` environment variable still works and overrides the stored token. 
- The `MATOMO_AI_TRACKING_ENABLED` environment variable overrides the "Track AI bots" setting, which the control panel then shows read-only. Use it to track only in production, also when its database is copied to other environments.
