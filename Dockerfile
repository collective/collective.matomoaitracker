# syntax=docker/dockerfile:1
ARG PLONE_VERSION=6.2.2
FROM plone/plone-backend:${PLONE_VERSION}

ARG PLONE_VERSION

COPY --chown=500:500 . /app/src/collective.matomoaitracker

RUN /app/bin/pip install --no-cache-dir \
        -c https://dist.plone.org/release/${PLONE_VERSION}/constraints.txt \
        /app/src/collective.matomoaitracker \
    && rm -rf /app/src/collective.matomoaitracker \
    && chown -R 500:500 "$(/app/bin/python -c 'import collective.matomoaitracker as p, os; print(os.path.dirname(p.__file__))')"

COPY scripts/create_site.py /app/scripts/create_matomoaitracker_site.py
COPY scripts/docker-start.sh /app/docker-start.sh

ENTRYPOINT ["/app/docker-start.sh"]
CMD ["start"]
