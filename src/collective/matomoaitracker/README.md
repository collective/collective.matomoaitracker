# collective.matomoaitracker

[![CI](https://github.com/collective/collective-matomoaitracker/actions/workflows/main.yml/badge.svg)](https://github.com/collective/collective-matomoaitracker/actions/workflows/main.yml)

A Plone addon for server-side tracking of AI chatbot requests in Matomo.

## Features 🚀

- Tracks AI bot requests in Matomo, including requests Varnish serves from its cache.
- Adds no work to the request path: Varnish only writes the bot category to its log.
- Sends AI assistants (Claude-User, ChatGPT-User, ...) to Matomo's AI Chatbots report.
- Optionally tracks every AI bot request, including search and training crawlers, as a
  visit in a separate Matomo site, with the bot category and the cache status as
  custom dimensions.
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
   URL, status, size, duration, cache status (`Varnish:handling`), User-Agent and
   referrer ([`varnishncsa/ai-bots.format`](../../../varnishncsa/ai-bots.format)).
3. The shipper ([`shipper/matomo_ai_shipper.py`](../../../shipper/matomo_ai_shipper.py),
   standard library only) follows that file and POSTs batches to `@@matomoaitracker`.
   It keeps its position in a small state file and only moves forward once Plone
   accepted a batch, so outages delay tracking. A batch can be sent twice when the
   shipper stops between sending and saving its position.
4. `@@matomoaitracker` checks the requests against the bot list in
   [`bots.py`](bots.py) and forwards them to Matomo's bulk tracking API, with `cdt` set
   to the time of the request:
   - `user`: to the Matomo site, as bot request (`recMode=1`), shown in the AI Chatbots
     report with status, size and duration. Matomo only stores AI assistants there.
   - every category, when an AI bots site is configured: as a visit (`bots=1`) with the
     client IP, referrer, and the custom dimensions.

## Configuration 🔧

In the **Matomo AI Chatbot Tracking** control panel:

- **Matomo Base URL** and **Matomo Site ID**.
- **Matomo AI bots Site ID** (optional): a separate site for all AI bot requests. Use a
  separate site, as these visits would otherwise mix with human visitors.
- **Bot category dimension ID** and **Cache status dimension ID** (optional): custom
  dimensions of the AI bots site, create them in Matomo first.

The Matomo `token_auth` is read from the `MATOMO_AI_TOKEN_AUTH` environment variable
of Plone, so it is not stored in the database. Matomo needs it for the original
request time and the client IP. Use the token of a user with write access to the
sites.

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
