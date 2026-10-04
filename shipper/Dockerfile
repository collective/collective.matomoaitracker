FROM python:3.13-slim

RUN useradd --system --uid 1000 shipper \
    && mkdir -p /var/lib/matomo-ai-shipper \
    && chown shipper /var/lib/matomo-ai-shipper

COPY --chmod=755 matomo_ai_shipper.py /usr/local/bin/matomo-ai-shipper

USER shipper

CMD ["matomo-ai-shipper", "--verbose"]
