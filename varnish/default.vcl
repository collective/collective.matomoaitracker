vcl 4.1;

# Varnish in front of the Nginx VirtualHostMonster proxy, which in turn
# proxies to Plone.  See docker-compose.yml.

import std;
import curl;

backend nginx {
    .host = "nginx";
    .port = "8002";
}

sub vcl_recv {
    # In production a TLS terminator in front of Varnish sets this header.
    if (!req.http.X-Forwarded-Proto) {
        set req.http.X-Forwarded-Proto = "http";
    }
}

sub vcl_deliver {
    include "varnish.vcl";
}
