#!/bin/bash
# Test the Varnish VCL against the running Docker stack (make stack-start).
#
# Requests go through Varnish; the tracking calls Varnish makes with
# libvmod-curl are checked in the Nginx access log.  Every request carries a
# unique marker in its URL so log lines can be matched to a single test.
#
# The tests run twice: first with the caching policy of the site (by default
# Plone does not let Varnish cache pages), then with pages mapped to
# plone.app.caching's moderateCaching so Varnish caches them.  The original
# policy is restored afterwards.  Changing the policy uses the REST API with
# PLONE_ADMIN credentials (default admin:admin).
#
# Note: every tracked request makes Plone send a hit to the configured
# MATOMO_BASE_URL.  To keep test hits out of Matomo, start the stack with a
# dummy Matomo first:
#
#   MATOMO_BASE_URL=http://nginx:8002/no-matomo make stack-start
set -u

cd "$(dirname "$0")/.."

# Ports blocked by Chrome and Firefox, see net/base/port_util.cc in Chromium.
BROWSER_BLOCKED_PORTS="1719 1720 1723 2049 3659 4045 4190 5060 5061 6000 6566 6665 6666 6667 6668 6669 6679 6697 10080"

# Test the ports the services are actually published on.
VARNISH_PORT=$(docker compose port varnish 80 2>/dev/null | sed 's/.*://')
PLONE_PORT=$(docker compose port plone 8080 2>/dev/null | sed 's/.*://')
if [[ -z "$VARNISH_PORT" || -z "$PLONE_PORT" ]]; then
    echo "Varnish or Plone is not running, start the stack first: make stack-start"
    exit 1
fi
VARNISH_URL="http://localhost:${VARNISH_PORT}"
PLONE_SITE_URL="http://localhost:${PLONE_PORT}/Plone"
PLONE_ADMIN="${PLONE_ADMIN:-admin:admin}"

# Seconds Varnish may cache pages with the moderateCaching policy.
SMAXAGE=60
OPERATION_MAPPING="plone.caching.interfaces.ICacheSettings.operationMapping"
MODERATE_SMAXAGE="plone.app.caching.moderateCaching.smaxage"

START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_ID="$(date +%s)$$"
COUNTER=0
PASSED=0
FAILED=0
SKIPPED=0

GREEN=$(tput setaf 2 2>/dev/null || true)
RED=$(tput setaf 1 2>/dev/null || true)
YELLOW=$(tput setaf 3 2>/dev/null || true)
BOLD=$(tput bold 2>/dev/null || true)
RESET=$(tput sgr0 2>/dev/null || true)

pass() {
    PASSED=$((PASSED + 1))
    echo "${GREEN}PASS${RESET} $1"
}

fail() {
    FAILED=$((FAILED + 1))
    echo "${RED}FAIL${RESET} $1"
}

skip() {
    SKIPPED=$((SKIPPED + 1))
    echo "${YELLOW}SKIP${RESET} $1"
}

# Set a unique marker for the URL of a test request.
new_marker() {
    COUNTER=$((COUNTER + 1))
    marker="vcltest${RUN_ID}x${COUNTER}end"
}

# Print the Nginx access log lines of tracking calls for a marker.
tracking_calls() {
    docker compose logs --no-log-prefix --since "$START_TIME" nginx 2>/dev/null \
        | grep "@@matomoaitracker" \
        | grep "$1"
}

count_tracking_calls() {
    tracking_calls "$1" | wc -l | tr -d ' '
}

# request PATH MARKER [curl options...]: request a page and print its status.
request() {
    local path="$1" marker="$2"
    shift 2
    curl -s -m 10 -o /dev/null -w '%{http_code}' "$@" \
        "${VARNISH_URL}${path}?marker=${marker}"
}

# x_varnish MARKER [curl options...]: print the X-Varnish header of a request.
x_varnish() {
    local marker="$1"
    shift
    curl -s -m 10 -o /dev/null -D - "$@" "${VARNISH_URL}/?marker=${marker}" \
        | grep -i '^x-varnish:' | tr -d '\r'
}

# Give Nginx a moment to flush its access log.
settle() {
    sleep 0.5
}

expect_tracked() {
    local description="$1" marker="$2" expected="${3:-1}"
    local count
    count=$(count_tracking_calls "$marker")
    if [[ "$count" == "$expected" ]]; then
        pass "$description"
    else
        fail "$description (expected $expected tracking call(s), got $count)"
    fi
}

# --- Caching policy ----------------------------------------------------------

registry_get() {
    curl -s -m 10 -u "$PLONE_ADMIN" -H 'Accept: application/json' \
        "${PLONE_SITE_URL}/@registry/$1"
}

# registry_set JSON: update registry records, print the HTTP status.
registry_set() {
    curl -s -m 10 -o /dev/null -w '%{http_code}' -u "$PLONE_ADMIN" -X PATCH \
        -H 'Accept: application/json' -H 'Content-Type: application/json' \
        -d "$1" "${PLONE_SITE_URL}/@registry"
}

restore_caching_policy() {
    if [[ -n "${original_mapping:-}" ]]; then
        status=$(registry_set "{\"${OPERATION_MAPPING}\": ${original_mapping}, \"${MODERATE_SMAXAGE}\": ${original_smaxage}}")
        if [[ "$status" == "204" ]]; then
            echo "Restored the original caching policy."
        else
            echo "${RED}Restoring the original caching policy failed (status ${status}).${RESET}"
        fi
        original_mapping=""
    fi
}

use_moderate_caching() {
    original_mapping=$(registry_get "$OPERATION_MAPPING")
    original_smaxage=$(registry_get "$MODERATE_SMAXAGE")
    if [[ "$original_mapping" != "{"* || ! "$original_smaxage" =~ ^[0-9]+$ ]]; then
        original_mapping=""
        echo "${RED}Could not read the caching policy, are the PLONE_ADMIN credentials right?${RESET}"
        return 1
    fi
    trap restore_caching_policy EXIT
    local mapping
    mapping=$(sed -E 's/("plone\.content\.(folderView|itemView)": )"[^"]*"/\1"plone.app.caching.moderateCaching"/g' <<<"$original_mapping")
    status=$(registry_set "{\"${OPERATION_MAPPING}\": ${mapping}, \"${MODERATE_SMAXAGE}\": ${SMAXAGE}}")
    if [[ "$status" != "204" ]]; then
        echo "${RED}Changing the caching policy failed (status ${status}).${RESET}"
        return 1
    fi
}

# --- Tests -------------------------------------------------------------------

# run_tests REQUIRE_CACHING: run all tests.  With REQUIRE_CACHING=yes a page
# Varnish may not cache fails the caching tests instead of skipping them.
run_tests() {
    local require_caching="$1"

    # An uncached URL, so the request has to go all the way to Plone.
    new_marker
    headers=$(curl -s -m 10 -o /dev/null -D - "${VARNISH_URL}/?marker=${marker}" | tr -d '\r')
    status=$(head -1 <<<"$headers" | cut -d' ' -f2)
    if [[ "$status" != "200" ]]; then
        fail "${VARNISH_URL} answers 200 (got '${status:-nothing}', is Plone still starting? make stack-logs)"
        return
    fi

    # Plone decides whether Varnish may cache the page (plone.app.caching).
    cache_control=$(grep -i '^cache-control:' <<<"$headers" | cut -d' ' -f2-)
    not_cacheable=""
    if grep -qiE 'private|no-cache|no-store|max-age=0' <<<"$cache_control" \
        && ! grep -qiE 's-maxage=[1-9]' <<<"$cache_control"; then
        not_cacheable="Plone does not allow caching the page: Cache-Control: ${cache_control}"
    fi
    echo "Cache-Control: ${cache_control:-none}"

    # Proxying and caching

    if grep -qi '^via:.*varnish' <<<"$headers"; then
        pass "Port ${VARNISH_PORT} is served by Varnish"
    else
        fail "Port ${VARNISH_PORT} is served by Varnish (no Varnish in the Via header)"
    fi

    if [[ " ${BROWSER_BLOCKED_PORTS} " == *" ${VARNISH_PORT} "* ]]; then
        fail "Port ${VARNISH_PORT} can be opened in a browser (Chrome and Firefox block it, set VARNISH_PORT in .env)"
    else
        pass "Port ${VARNISH_PORT} can be opened in a browser"
    fi

    new_marker
    body=$(curl -s -m 10 "${VARNISH_URL}/?marker=${marker}")
    if grep -q "href=\"${VARNISH_URL}/" <<<"$body"; then
        pass "VirtualHostMonster links point to ${VARNISH_URL}"
    else
        fail "VirtualHostMonster links point to ${VARNISH_URL}"
    fi

    if [[ -n "$not_cacheable" && "$require_caching" != "yes" ]]; then
        skip "Second request is a cache hit ($not_cacheable)"
    else
        new_marker
        request / "$marker" >/dev/null
        hit=$(x_varnish "$marker")
        if [[ $(wc -w <<<"$hit") -eq 3 ]]; then
            pass "Second request is a cache hit"
        else
            fail "Second request is a cache hit ($hit; ${not_cacheable:-Cache-Control: $cache_control})"
        fi
    fi

    # AI chatbots are tracked

    BOTS=$(sed -n 's/.*(?i)(\([^)]*\)).*/\1/p' varnish/varnish.vcl | tr '|' ' ')
    if [[ -z "$BOTS" ]]; then
        fail "Read the AI chatbot User-Agents from varnish/varnish.vcl"
    fi

    for bot in $BOTS; do
        new_marker
        status=$(request / "$marker" -A "Mozilla/5.0 (compatible; ${bot}/1.0)")
        settle
        if [[ "$status" != "200" ]]; then
            fail "$bot gets the page (status $status)"
            continue
        fi
        line=$(tracking_calls "$marker")
        if [[ -z "$line" ]]; then
            fail "$bot is tracked"
        elif ! grep -q "${bot}/1.0" <<<"$line"; then
            fail "$bot is tracked (User-Agent not passed on: $line)"
        elif grep -q "\" 499 " <<<"$line"; then
            pass "$bot is tracked ${YELLOW}(Varnish stopped waiting for Plone, is Matomo slow?)${RESET}"
        elif ! grep -q "\" 204 " <<<"$line"; then
            fail "$bot is tracked (tracking view did not answer 204: $line)"
        else
            pass "$bot is tracked"
        fi
    done

    new_marker
    request / "$marker" -A "Mozilla/5.0 (compatible; claudebot/1.0)" >/dev/null
    settle
    expect_tracked "User-Agent match is case insensitive" "$marker"

    if [[ -n "$not_cacheable" && "$require_caching" != "yes" ]]; then
        skip "Cache hits are tracked too ($not_cacheable)"
    else
        new_marker
        request / "$marker" -A "ClaudeBot/1.0" >/dev/null
        hit=$(x_varnish "$marker" -A "ClaudeBot/1.0")
        settle
        if [[ $(wc -w <<<"$hit") -ne 3 ]]; then
            fail "Cache hits are tracked too (second request was not a cache hit: $hit)"
        else
            expect_tracked "Cache hits are tracked too" "$marker" 2
        fi
    fi

    # Tracked URL

    new_marker
    request /news "$marker" -A "ClaudeBot/1.0" >/dev/null
    settle
    expected_url="url=http%3A%2F%2F${VARNISH_URL#http://}%2Fnews%3Fmarker%3D${marker}"
    expected_url="${expected_url//:/%3A}"
    if tracking_calls "$marker" | grep -q "$expected_url"; then
        pass "Tracked URL is the full public URL"
    else
        fail "Tracked URL is the full public URL (expected $expected_url in: $(tracking_calls "$marker"))"
    fi

    new_marker
    request / "$marker" -A "ClaudeBot/1.0" -H "X-Forwarded-Proto: https" >/dev/null
    settle
    if tracking_calls "$marker" | grep -q "url=https%3A%2F%2F"; then
        pass "X-Forwarded-Proto https is used in the tracked URL"
    else
        fail "X-Forwarded-Proto https is used in the tracked URL"
    fi

    # Requests that are not tracked

    new_marker
    request / "$marker" -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Firefox/140.0" >/dev/null
    settle
    expect_tracked "Browsers are not tracked" "$marker" 0

    new_marker
    request / "$marker" -A "" >/dev/null
    settle
    expect_tracked "Requests without User-Agent are not tracked" "$marker" 0

    new_marker
    request / "$marker" -A "ClaudeBot/1.0" -H "X-Forwarded-Proto: ftp" >/dev/null
    settle
    expect_tracked "Unknown X-Forwarded-Proto is not tracked" "$marker" 0
}

# --- Main --------------------------------------------------------------------

matomo_base_url=$(docker compose exec -T plone printenv MATOMO_BASE_URL 2>/dev/null)
echo "Testing Varnish at ${VARNISH_URL}, Plone tracks in Matomo at ${matomo_base_url:-?}"
if [[ "$matomo_base_url" != http://nginx:* ]]; then
    echo "${YELLOW}Every tracked test request sends a hit to this Matomo.${RESET}"
fi

echo
echo "${BOLD}== Caching policy of the site${RESET}"
run_tests no

echo
echo "${BOLD}== Pages with moderateCaching (s-maxage=${SMAXAGE})${RESET}"
if use_moderate_caching; then
    run_tests yes
    restore_caching_policy
else
    fail "Switch pages to moderateCaching"
fi

echo
echo "${PASSED} passed, ${FAILED} failed, ${SKIPPED} skipped"
[[ "$FAILED" -eq 0 ]]
