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

Tracks the requests of AI bots in Matomo, also when Varnish serves them from its
cache, without slowing them down:

- Varnish classifies AI bots by User-Agent as `user` (an AI assistant fetching a page
  for a user, like Claude-User or ChatGPT-User), `search` (AI search crawlers) or
  `training` (training data crawlers), and writes that to its log.
- varnishncsa writes these requests to a log file, and a small shipper sends them in
  batches to Plone. When Plone or Matomo is down, tracking is delayed, not lost.
- Plone forwards them to Matomo's bulk tracking API, with the original time of the
  request. Requests for the resources of pages, like images, styles and scripts, are
  skipped, and documents like PDFs are tracked as downloads:
  - `user` requests go to Matomo's **AI Chatbots** report (Matomo 5.8 or later).
  - Optionally all AI bot requests go to a separate Matomo site as visits, with the
    bot category, bot name and the Varnish cache status (hit, miss, pass) as custom dimensions.

The control panel "Matomo AI Chatbot Tracking" has the Matomo settings. See
[the add-on's README](src/collective/matomoaitracker/README.md) for setting up
Varnish, varnishncsa and the shipper.

## Installation

Install collective.matomoaitracker with `pip`:

```shell
pip install collective.matomoaitracker
```

And to create the Plone site:

```shell
make create-site
```

This Addon expects you to run a varnish, varnishnsca and shipper Docker image.
Examples can be found in the subfolder for each service.


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

The full stack runs in Docker:

```text
requests:  Varnish (8001) -> Nginx VirtualHostMonster (8002) -> Plone site "Plone" (8003)
tracking:  Varnish log -> varnishncsa -> ai-bots.log -> shipper -> Plone -> Matomo (8004)
```

Varnish's configuration (`varnish/default.vcl`) is based on the one of Plone's
cookieplone project templates, tuned for plone.app.caching: Plone purges changed
content from Varnish, logged-in users are not cached. For the tracking, Varnish only
classifies AI bots and writes the result to its log, it makes no HTTP calls. varnishncsa writes the AI bot requests to a log file, which the shipper sends
in batches to Plone, and Plone forwards them to Matomo. By default that is a fake
Matomo, which records what it receives for the tests.

```shell
make stack-start
```

On start the Plone site is created, the Matomo settings are applied and the service
user for the shipper is created. Settings can be overridden with environment
variables or in a `.env` file, see `.env.example`:

```shell
cp .env.example .env
```

Note: if you change anything to the `create_site.py` script, you must remove the
`matomoaitracker-plone` image, otherwise this has no effect.

Simulate an AI chatbot visit, and see what reached the fake Matomo a few seconds
later:

```shell
curl -A "Claude-User/1.0" http://localhost:8001/
curl http://localhost:8004/_requests
```

Test the VCL and the varnishncsa format with `varnishtest`:

```shell
make varnish-test
```

Test the whole tracking chain against the running stack with the fake Matomo:
every AI bot is tracked once in the right category, also from the cache, other
requests are not, bots are not slowed down, and outages of Matomo or the shipper
delay tracking without losing it. These are the pytest tests in `tests/stack`, which
`make test` skips because they need the stack:

```shell
make stack-test
```

The tests run with Plone's caching policy, and again with pages cached in Varnish for
60 seconds (`moderateCaching`), restoring the policy afterwards. They log in to Plone's
REST API as `admin:admin` for that, set `PLONE_ADMIN=user:password` for other
credentials.

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
