# collective.matomoaitracker

[![CI](https://github.com/collective/collective-matomoaitracker/actions/workflows/main.yml/badge.svg)](https://github.com/collective/collective-matomoaitracker/actions/workflows/main.yml)

A Plone addon for server-side tracking of AI chatbot requests in Matomo.

## Features 🚀

- Provides a Plone control panel for the Matomo Site ID and Base URL.
- Sends Matomo tracking requests for AI chatbot visits detected by an upstream Varnish configuration.
- Keeps tracking failures from affecting the normal page response.
- Provides tests for the control panel and tracking view.

## Installation 🔧

Clone the repository and install the addon development environment:

```shell
git clone git@github.com:collective/collective-matomoaitracker.git
cd collective-matomoaitracker
make install
```

The addon can also be added to an existing Plone project as a Python dependency. Install it through that project's normal dependency workflow, then activate the `collective.matomoaitracker:default` profile.

## Configuration ⚙️

After installing the addon, open the **Matomo AI Chatbot** control panel and configure:

- **Matomo Site ID**
- **Matomo Base URL**

The control-panel values are stored in the Plone registry and are the runtime source of truth.

## Varnish Integration 🧊

[`varnish/varnish.vcl`](../../../varnish/varnish.vcl) is a `vcl_deliver` insertion snippet for the generated VCL from `plone.recipe.varnish` 6.0.18. Put its contents in that recipe's `vcl_deliver` option; the generated file already imports `std` and defines the surrounding subroutine. Do not load the snippet as a replacement VCL file.

For recognized AI user agents, the snippet writes a `VCL_Log` record containing `MATOMO_AI_TRACK` and the original User-Agent. This avoids an HTTP request in VCL, so cache-hit delivery is not delayed. A cron process should select transactions with that marker, take the path from `ReqURL`, the host from `ReqHeader:Host`, and the scheme from `ReqHeader:X-Forwarded-Proto`, then POST a JSON batch to the Plone origin's `@@matomoaitracker` view:

```json
{
	"events": [
		{
			"url": "https://example.org/page",
			"user_agent": "GPTBot/1.0"
		}
	]
}
```

The view requires the `cmf.ManagePortal` permission, so the cron caller must authenticate with a JWT Bearer token belonging to an authorized account. It returns a `results` array of booleans in input order; retry only events whose result is `false`. The view limits batches to 100 events and rejects malformed, non-HTTP(S), or oversized values before tracking.

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
