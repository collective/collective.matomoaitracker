FROM varnish:9.1.0

# libvmod-curl commit compatible with Varnish 9.1
ARG VMOD_CURL_COMMIT=dd44d119470c2b6d484adf5cfb53f053b6a18b21

USER root

RUN set -ex; \
    export DEBIAN_FRONTEND=noninteractive; \
    VARNISH_PKG_VERSION="$(dpkg-query -W -f='${Version}' varnish)"; \
    BUILD_DEPS="autoconf-archive automake curl libtool make pkg-config python3-docutils libcurl4-openssl-dev varnish-dev=${VARNISH_PKG_VERSION}"; \
    apt-get update; \
    apt-get install -y --no-install-recommends libcurl4t64 $BUILD_DEPS; \
    install-vmod "https://github.com/varnish/libvmod-curl/archive/${VMOD_CURL_COMMIT}.tar.gz"; \
    apt-get -y purge --auto-remove $BUILD_DEPS; \
    rm -rf /var/lib/apt/lists/* /usr/lib/varnish/vmods/libvmod_*.la

COPY default.vcl varnish.vcl /etc/varnish/

USER varnish
