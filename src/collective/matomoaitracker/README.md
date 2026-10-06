# collective.matomoaitracker

[![CI](https://github.com/collective/collective-matomoaitracker/actions/workflows/main.yml/badge.svg)](https://github.com/collective/collective-matomoaitracker/actions/workflows/main.yml)

A Plone addon for server-side tracking of AI chatbot requests in Matomo.

## Features 🚀

- Tracks AI bot requests in Matomo, including requests Varnish serves from its cache.
- Adds no work to the request path: Varnish only writes the bot category to its log.
- Sends AI assistants (Claude-User, ChatGPT-User, ...) to Matomo's AI Chatbots report.
- Optionally tracks every AI bot request, including search and training crawlers, as a
  visit in a separate Matomo site, with the bot category, the cache status and the bot
  name as custom dimensions. Matomo's AI Assistants reports leave crawlers out; this
  site shows which crawlers cause load peaks, and how much of it reached Plone.
- Only tracks pages and documents, not the images, styles and scripts of pages: the
  excluded URLs can be changed in the control panel.
- Tracks documents, like PDFs, as downloads.
- Delays tracking during a Plone or Matomo outage instead of losing it.

## Installation 🔧

Clone the repository and install the addon development environment:

```shell
git clone git@github.com:collective/collective-matomoaitracker.git
cd collective-matomoaitracker
make install
```

The addon can also be added to an existing Plone project as a Python dependency. Install it through that project's normal dependency workflow, then activate the `collective.matomoaitracker:default` profile.

## How it works ⚙️

```text
Varnish ──(VCL_Log ai-bot:<category>)──> varnishncsa ──> /var/log/varnish/ai-bots.log
                                                                │
Matomo <── bulk tracking API ── Plone @@matomoaitracker <── shipper (batches, retries)
```

1. [`varnish/matomoaitracker.vcl`](../../../varnish/matomoaitracker.vcl) classifies the
   User-Agent in `vcl_recv` as `user`, `search` or `training`, and logs it with
   `std.log("ai-bot:<category>")`. A log record cannot be faked by clients, unlike a
   request header.
2. varnishncsa writes every logged AI bot request as a JSON line, with time, client IP,
   URL, status, size, content type, duration, cache status (`Varnish:handling`),
   User-Agent and referrer ([`varnishncsa/ai-bots.format`](../../../varnishncsa/ai-bots.format)).
3. The shipper ([`shipper/matomo_ai_shipper.py`](../../../shipper/matomo_ai_shipper.py),
   standard library only) follows that file and POSTs batches to `@@matomoaitracker`.
   It keeps its position in a small state file and only moves forward once Plone
   accepted a batch, so outages delay tracking. A batch can be sent twice when the
   shipper stops between sending and saving its position.
4. `@@matomoaitracker` checks the requests against the bot list in
   [`bots.py`](bots.py) and forwards them to Matomo's bulk tracking API, with `cdt` set
   to the time of the request. Requests for excluded URLs are skipped, and responses
   with a document content type (not a page, like `application/pdf`) are sent as
   downloads:
   - `user`: to the Matomo site, as bot request (`recMode=1`, `source=Varnish`), shown in
     the AI Chatbots report with status, size and duration. Matomo only stores AI
     assistants there.
   - every category, when an AI bots site is configured: as a visit (`bots=1`) with the
     client IP, referrer, duration (Matomo's Performance report), and the custom
     dimensions.

## Configuration 🔧

In the **Matomo AI Chatbot Tracking** control panel:

- **Track AI bots**: switch tracking off and on. While it is off, AI bot requests are
  dropped, not tracked later. The `MATOMO_AI_TRACKING_ENABLED` environment variable of
  Plone overrides it (`true` or `false`, any other value is `false`), and the control
  panel then shows it read-only. Use it when a production database is copied to test
  environments that should not track.
- **Matomo Base URL** and **Matomo Site ID**.
- **Matomo AI bots Site ID** (optional): a separate site for all AI bot requests. Use a
  separate site, as these visits would otherwise mix with human visitors.
- **Categories tracked in the AI bots site**: AI assistants, search crawlers and
  training crawlers, all by default.
- **Bot category dimension ID**, **Cache status dimension ID** and **Bot name dimension
  ID** (optional): custom dimensions of the AI bots site, create them in Matomo first.
  Action scope works best: a crawler's requests are grouped in a few long visits.

To see crawler load in the AI bots site, use the actions (page views) per hour rather
than the visits, broken down by the bot name and cache status dimensions: misses and
passes are the requests that reached Plone.
- **Excluded URLs**: regular expressions for URL paths that are not tracked. By default
  Plone's resources (`++resource++`, `++plone++`, `++theme++`, `@@images`) and files like
  styles, scripts, images and fonts.

**Test connection** checks the saved settings against Matomo: whether the sites exist
for the token, and whether the custom dimensions exist and are active.

Above the settings, **Tracking status** shows when the shipper last delivered a batch,
how many tracking requests were sent, rejected by Matomo or not tracked, and the last
error. It is kept in memory: it counts what the Zope instance showing the control panel
handled since it started.

**Matomo token**: create an auth token in Matomo under *Personal* > *Security* for a
user with write access to the sites, and paste it. Matomo needs it for the original
request time and the client IP. The token is never shown again, not even in the page
source: leave the field empty to keep it, or use **Remove token**. It is stored in the
Plone registry, which only Managers and Site Administrators can read. To keep it out
of the database, set the `MATOMO_AI_TOKEN_AUTH` environment variable of Plone instead:
it overrides the stored token.

Submitting requests to `@@matomoaitracker` needs the permission
`collective.matomoaitracker: Submit tracking events`. Create a user for the shipper with
the **Matomo AI Tracker** role, which only has this permission.

## Varnish integration 🧊

Include the VCL at the top level of your VCL, after `import std;`:

```vcl
import std;
include "matomoaitracker.vcl";
```

It defines `vcl_recv` and `vcl_backend_fetch` code, which Varnish runs before your own.
It also blocks `@@matomoaitracker` from the outside: the shipper calls Plone directly.

For varnishncsa and the shipper, see the systemd units and logrotate configuration in
[`varnishncsa/`](../../../varnishncsa/) and [`shipper/`](../../../shipper/):

```shell
cp varnishncsa/ai-bots.format /etc/varnish/
cp varnishncsa/matomo-ai-varnishncsa.service shipper/matomo-ai-shipper.service /etc/systemd/system/
cp varnishncsa/matomo-ai.logrotate /etc/logrotate.d/matomo-ai
install -m 755 shipper/matomo_ai_shipper.py /usr/local/bin/matomo-ai-shipper
install -d -m 700 /etc/matomo-ai-shipper   # put the service user's password in ./password
systemctl enable --now matomo-ai-varnishncsa matomo-ai-shipper
```

The shipper is configured with environment variables or options, see
`matomo-ai-shipper --help`. When a TLS terminator in front of Varnish does not send
`X-Forwarded-Proto`, use `--default-scheme https`.

## Development 🛠️

Run formatting, linting, and tests with:

```shell
make check
```

Run tests only with:

```shell
make test
```

## License 📄

This project is licensed under GPLv2.

## Credits 🙏

Generated using [Cookieplone](https://github.com/plone/cookieplone/).
