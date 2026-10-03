#!/bin/bash
# Create (or update) the Plone site before starting the backend.
set -e

if [[ "$1" == "start" ]]; then
  /app/docker-entrypoint.sh run /app/scripts/create_matomoaitracker_site.py
fi

exec /app/docker-entrypoint.sh "$@"
