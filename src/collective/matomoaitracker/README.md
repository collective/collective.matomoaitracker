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

The addon does not impose a deployment-specific Varnish image or compose stack. Configure Varnish to identify the chatbot User-Agent and call:

```text
/@@matomoaitracker?url=<requested-page-url>
```

The tracking view returns `204` and is designed to be called as a side request while Varnish delivers the requested cached response. The Varnish configuration must provide the appropriate HTTP client VMOD and route the internal request to Plone.

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
