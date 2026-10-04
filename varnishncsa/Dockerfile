FROM varnish:9.1.0

# Writes every AI bot request Varnish delivers as a JSON line to
# /var/log/varnish/ai-bots.log, for the shipper.  Needs Varnish's working
# directory (/var/lib/varnish/varnishd) shared with the varnish container.

USER root
RUN mkdir -p /var/log/varnish && chown varnish:varnish /var/log/varnish
COPY ai-bots.format /etc/varnish/ai-bots.format
USER varnish

CMD ["varnishncsa", "-c", "-j", "-a", "-t", "off", \
     "-q", "VCL_Log:ai-bot", \
     "-f", "/etc/varnish/ai-bots.format", \
     "-w", "/var/log/varnish/ai-bots.log"]
