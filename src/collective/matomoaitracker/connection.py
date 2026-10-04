"""Check the Matomo settings against Matomo, for the control panel."""

import requests


TIMEOUT = 10


class MatomoAPIError(Exception):
    """Matomo's API could not be called or answered with an error."""


def call_api(settings, method, **params):
    """Call a method of Matomo's reporting API, return its result."""
    try:
        response = requests.post(
            settings["base_url"] + "index.php",
            # The token in the body: URLs end up in access logs.
            data={
                "module": "API",
                "method": method,
                "format": "json",
                "token_auth": settings["token_auth"],
                **params,
            },
            timeout=TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as error:
        raise MatomoAPIError(f"Cannot reach Matomo: {error}") from error
    if response.status_code != 200:
        raise MatomoAPIError(f"Matomo answered HTTP {response.status_code}")
    try:
        result = response.json()
    except ValueError as error:
        raise MatomoAPIError("Matomo did not answer with JSON") from error
    if isinstance(result, dict) and result.get("result") == "error":
        raise MatomoAPIError(result.get("message", "Unknown error"))
    return result


def check_connection(settings):
    """Check the sites and dimensions, return (ok, message) tuples."""
    results = []
    sites = [("Matomo Site ID", settings["site_id"])]
    if settings["bot_site_id"]:
        sites.append(("AI bots Site ID", settings["bot_site_id"]))
    for label, site_id in sites:
        try:
            site = call_api(settings, "SitesManager.getSiteFromId", idSite=site_id)
        except MatomoAPIError as error:
            results.append((False, f"{label} {site_id}: {error}"))
            continue
        results.append((True, f"{label} {site_id}: {site.get('name', '?')}"))

    dimensions = [
        (label, settings[key])
        for label, key in (
            ("Bot category dimension", "dimension_category"),
            ("Cache status dimension", "dimension_cache"),
            ("Bot name dimension", "dimension_bot"),
        )
        if settings[key]
    ]
    if not settings["bot_site_id"] or not dimensions:
        return results
    try:
        configured = call_api(
            settings,
            "CustomDimensions.getConfiguredCustomDimensions",
            idSite=settings["bot_site_id"],
        )
    except MatomoAPIError as error:
        results.append((False, f"Custom dimensions of the AI bots site: {error}"))
        return results
    by_id = {
        str(dimension.get("idcustomdimension")): dimension
        for dimension in configured
        if isinstance(dimension, dict)
    }
    for label, dimension_id in dimensions:
        dimension = by_id.get(str(dimension_id))
        if dimension is None:
            results.append((
                False,
                f"{label} {dimension_id}: not found in the AI bots site",
            ))
        elif not dimension.get("active"):
            results.append((False, f"{label} {dimension_id}: not active"))
        else:
            results.append((
                True,
                f"{label} {dimension_id}: {dimension.get('name')} "
                f"({dimension.get('scope')} scope)",
            ))
    return results
