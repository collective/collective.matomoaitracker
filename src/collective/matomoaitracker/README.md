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

The addon does not impose a deployment-specific Varnish image or compose stack. [`varnish/varnish.vcl`](../../../varnish/varnish.vcl) is a `vcl_deliver` insertion snippet for Varnish 6.0.18. Add `import curl;` at the top level of the generated VCL, then put the snippet contents in that recipe's `vcl_deliver` option. The generated VCL already imports `std`. Set `MATOMO_AI_PLONE_ORIGIN` in the Varnish service environment to the internal HTTP origin, for example `http://plone:8080`, and ensure requests carry `X-Forwarded-Proto` set to `http` or `https`.

For known AI bot User-Agents, the snippet uses the curl VMOD to synchronously call:

```text
${MATOMO_AI_PLONE_ORIGIN}/@@matomoaitracker?url=<percent-encoded-requested-page-url>
```

It forwards the original User-Agent header and escapes the complete requested page URL. The curl connection timeout is 250 ms and the total timeout is 1 second; because the VMOD call is synchronous, it can delay delivery by up to that timeout. Use an internal HTTP Plone origin: the curl VMOD documents HTTPS connections as unsupported.

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
