<div align="center">
    <h1 align="center">collective.matomoaitracker</h1>
</div>
<div align="center">
[![PyPI](https://img.shields.io/pypi/v/collective.matomoaitracker)](https://pypi.org/project/collective.matomoaitracker/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/collective.matomoaitracker)](https://pypi.org/project/collective.matomoaitracker/)
[![PyPI - Wheel](https://img.shields.io/pypi/wheel/collective.matomoaitracker)](https://pypi.org/project/collective.matomoaitracker/)
[![PyPI - License](https://img.shields.io/pypi/l/collective.matomoaitracker)](https://pypi.org/project/collective.matomoaitracker/)
[![PyPI - Status](https://img.shields.io/pypi/status/collective.matomoaitracker)](https://pypi.org/project/collective.matomoaitracker/)


[![PyPI - Plone Versions](https://img.shields.io/pypi/frameworkversions/plone/collective.matomoaitracker)](https://pypi.org/project/collective.matomoaitracker/)

[![CI](https://github.com/collective/collective.matomoaitracker/actions/workflows/main.yml/badge.svg)](https://github.com/collective/collective.matomoaitracker/actions/workflows/main.yml)
![Code Style](https://img.shields.io/badge/Code%20Style-Black-000000)

[![GitHub contributors](https://img.shields.io/github/contributors/collective/collective.matomoaitracker)](https://github.com/collective/collective.matomoaitracker)
[![GitHub Repo stars](https://img.shields.io/github/stars/collective/collective.matomoaitracker?style=social)](https://github.com/collective/collective.matomoaitracker)

</div>

A addon for Plone which allow you to track requests from AI Chatbots to the server in Matomo.

## Features

After installing this addon in the Site Setting menu a new control panel "Matomo AI Tracker"
is available to set the Matomo Site Id and Matomo Base URL.

A view is available to track a url visited by an AI Chatbot.

```
    /@@matomoaitracker?url=https://www.example.com/deep/location/detail.html
```

This view is expected to be used from the Varnish caching server which runs in front of Plone
backend. Varnish will check the User-Agent header and if it's one of the known AI providers
it will use `curl` to call the backend and return the cached page.

## Installation

Install collective.matomoaitracker with `pip`:

```shell
pip install collective.matomoaitracker
```

And to create the Plone site:

```shell
make create-site
```

## Contribute

- [Issue tracker](https://github.com/collective/collective.matomoaitracker/issues)
- [Source code](https://github.com/collective/collective.matomoaitracker/)

### Prerequisites ✅

-   An [operating system](https://6.docs.plone.org/install/create-project-cookieplone.html#prerequisites-for-installation) that runs all the requirements mentioned.
-   [uv](https://6.docs.plone.org/install/create-project-cookieplone.html#uv)
-   [Make](https://6.docs.plone.org/install/create-project-cookieplone.html#make)
-   [Git](https://6.docs.plone.org/install/create-project-cookieplone.html#git)
-   [Docker](https://docs.docker.com/get-started/get-docker/) (optional)

### Development Installation 🔧

1.  Clone this repository, then change your working directory.

    ```shell
    git clone git@github.com:collective/collective.matomoaitracker.git
    cd collective.matomoaitracker
    ```

2.  Install this code base. This also builds the Docker images for the full stack.

    ```shell
    make install
    ```

### Docker stack 🐳

The full stack runs in Docker: Varnish with `libvmod-curl` on port 10080, in front of
Nginx on port 9080, which does the VirtualHostMonster rewrites to the Plone site
`Plone`. On start the Plone site is created and the Matomo settings are applied.

```shell
make stack-start
```

Matomo is configured with `MATOMO_BASE_URL` (default `https://matomo.example.com`)
and `MATOMO_SITE_ID` (default `1`):

```shell
MATOMO_BASE_URL=https://matomo.example.com MATOMO_SITE_ID=3 make stack-start
```

These settings can also be put in a `.env` file, see `.env.example`:

```shell
cp .env.example .env
```

Simulate an AI chatbot visit:

```shell
curl -A "ClaudeBot/1.0" http://localhost:10080/
```

Other targets: `make stack-logs`, `make stack-stop` and `make stack-remove-data`.


### Add features using `plonecli` or `bobtemplates.plone`

This package provides markers as strings (`<!-- extra stuff goes here -->`) that are compatible with [`plonecli`](https://github.com/plone/plonecli) and [`bobtemplates.plone`](https://github.com/plone/bobtemplates.plone).
These markers act as hooks to add all kinds of subtemplates, including behaviors, control panels, upgrade steps, or other subtemplates from `plonecli`.

To run `plonecli` with configuration to target this package, run the following command.

```shell
make add <template_name>
```

For example, you can add a content type to your package with the following command.

```shell
make add content_type
```

You can add a behavior with the following command.

```shell
make add behavior
```

```{seealso}
You can check the list of available subtemplates in the [`bobtemplates.plone` `README.md` file](https://github.com/plone/bobtemplates.plone/?tab=readme-ov-file#provided-subtemplates).
See also the documentation of [Mockup and Patternslib](https://6.docs.plone.org/classic-ui/mockup.html) for how to build the UI toolkit for Classic UI.
```

## License

The project is licensed under GPLv2.

## Credits and acknowledgements 🙏

Generated using [Cookieplone (2.0.0)](https://github.com/plone/cookieplone) and [cookieplone-templates (fa8eca4)](https://github.com/plone/cookieplone-templates/commit/fa8eca4f3ea456538542b6b07f9bceaa05127fd2) on 2026-09-30 17:16:12.816436. A special thanks to all contributors and supporters!
