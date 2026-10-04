#!/usr/bin/env python3
"""Ship AI bot requests from the varnishncsa log to collective.matomoaitracker.

varnishncsa writes one JSON line per AI bot request to a log file (see
varnishncsa/ai-bots.format).  This program follows that file, and POSTs the
requests in batches to the @@matomoaitracker view of the Plone site, which
forwards them to Matomo.

The log file is the buffer: when Plone or Matomo is down, the shipper retries
the same batch with an increasing delay, while varnishncsa keeps appending.
The position in the log file is kept in a small state file, and only moves
forward once a batch is accepted, so after a restart the shipper continues
where it was.  A batch can be sent twice when the shipper stops between
sending it and saving the position.

Log rotation by renaming (logrotate's default, with a postrotate that sends
SIGHUP to varnishncsa) and by copytruncate are both followed.

Only uses the Python standard library, so it can run on the Varnish host.
"""

from argparse import ArgumentParser
from base64 import b64encode
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import build_opener
from urllib.request import HTTPRedirectHandler
from urllib.request import Request

import json
import logging
import os
import signal
import threading
import time


logger = logging.getLogger("matomo_ai_shipper")

# Responses after which sending the same batch again cannot succeed.
PERMANENT_FAILURES = frozenset((400, 405, 413, 422))


def to_event(line, default_scheme="http"):
    """Convert a varnishncsa JSON line to an event for the Plone view.

    Returns None for lines that cannot be used.
    """
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    host = data.get("host", "")
    path = data.get("url", "")
    if not host or not path.startswith("/"):
        return None
    scheme = data.get("proto", "").split(",")[0].strip().lower()
    if scheme not in ("http", "https"):
        scheme = default_scheme
    timestamp = to_int(data.get("time"))
    if timestamp is None:
        return None

    # Varnish appends the address it received the request from to
    # X-Forwarded-For, so the first address is the original client.
    forwarded_for = data.get("forwarded_for", "").split(",")[0].strip()
    duration_us = to_int(data.get("duration_us"))
    event = {
        "time": timestamp,
        "url": f"{scheme}://{host}{path}",
        "user_agent": data.get("user_agent", ""),
        "ip": forwarded_for or data.get("client_ip") or None,
        "referrer": data.get("referrer") or None,
        "status": to_int(data.get("status")),
        "bytes": to_int(data.get("bytes")),
        "duration_ms": round(duration_us / 1000) if duration_us is not None else None,
        "cache": data.get("handling") or None,
    }
    return {key: value for key, value in event.items() if value is not None}


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class State:
    """The inode and byte offset of the next line to ship."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            data = json.loads(self.path.read_text())
            return int(data["inode"]), int(data["offset"])
        except (OSError, ValueError, KeyError, TypeError):
            return None, 0

    def save(self, inode, offset):
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps({"inode": inode, "offset": offset}))
        os.replace(temporary, self.path)


class LogReader:
    """Read complete lines from a log file, following rotation."""

    def __init__(self, path, inode=None, offset=0):
        self.path = Path(path)
        self.file = None
        self.inode = None
        self.rotated = False
        self.open(inode, offset)

    def open(self, inode, offset):
        """Open the file at the saved position, if it still exists."""
        if inode is not None:
            # After a rotation the saved file may have been renamed.
            for candidate in (self.path, self.path.with_name(self.path.name + ".1")):
                if self.inode_of(candidate) == inode:
                    self.open_file(candidate, offset)
                    self.rotated = candidate != self.path
                    return
            logger.warning(
                "%s was rotated more than once, continuing with the new file",
                self.path,
            )
        if self.path.exists():
            self.open_file(self.path, 0)

    def open_file(self, path, offset):
        if self.file:
            self.file.close()
        self.file = open(path, "rb")  # noqa: SIM115 - kept open while following
        self.inode = os.fstat(self.file.fileno()).st_ino
        size = os.fstat(self.file.fileno()).st_size
        self.file.seek(offset if offset <= size else 0)

    @staticmethod
    def inode_of(path):
        try:
            return path.stat().st_ino
        except OSError:
            return None

    @property
    def offset(self):
        return self.file.tell() if self.file else 0

    def read_lines(self, limit):
        """Return up to `limit` complete lines, following rotation.

        Afterwards `inode` and `offset` point just after the last line.
        """
        if self.file is None:
            if not self.path.exists():
                return []
            self.open_file(self.path, 0)

        # copytruncate: the file is shorter than where we are.
        if os.fstat(self.file.fileno()).st_size < self.file.tell():
            logger.info("%s was truncated, reading it from the start", self.path)
            self.file.seek(0)

        lines = self.read_complete_lines(limit)
        if lines or not self.rotated_away():
            return lines
        # Lines may have been written between reading and the rotation.
        lines = self.read_complete_lines(limit)
        if lines:
            return lines
        if self.path.exists():
            logger.info("%s was rotated, continuing with the new file", self.path)
            self.open_file(self.path, 0)
            self.rotated = False
        return []

    def read_complete_lines(self, limit):
        lines = []
        while len(lines) < limit:
            start = self.file.tell()
            line = self.file.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                # varnishncsa is still writing this line.
                self.file.seek(start)
                break
            lines.append(line)
        return lines

    def rotated_away(self):
        """Whether a new file replaced the one being read."""
        current_inode = self.inode_of(self.path)
        return self.rotated or current_inode not in (None, self.inode)


class PloneClient:
    """POST batches of events to the @@matomoaitracker view."""

    def __init__(self, url, username, password, timeout=30):
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"The Plone URL must be an HTTP(S) URL: {url}")
        self.url = url.rstrip("/") + "/@@matomoaitracker"
        credentials = b64encode(f"{username}:{password}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.timeout = timeout
        # A redirect means the login failed: never follow it, urllib would
        # turn the POST into a GET of the login form.
        self.opener = build_opener(NoRedirects)

    def send(self, events):
        """Send events, return True when done and False to retry later."""
        # The scheme of the URL is checked in __init__.
        request = Request(  # noqa: S310
            self.url,
            data=json.dumps({"events": events}).encode("utf-8"),
            headers=self.headers,
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                result = json.loads(response.read())
        except HTTPError as error:
            if error.code in PERMANENT_FAILURES:
                logger.error(
                    "Plone refused a batch of %s request(s), dropping it: HTTP %s %s",
                    len(events),
                    error.code,
                    error.read()[:200],
                )
                return True
            logger.warning("Plone answered HTTP %s, retrying later", error.code)
            return False
        except (URLError, OSError, ValueError) as error:
            logger.warning("Cannot reach Plone (%s), retrying later", error)
            return False
        if not isinstance(result, dict) or "tracked" not in result:
            logger.warning("Unexpected answer from Plone, retrying later: %r", result)
            return False
        logger.info(
            "Shipped %s request(s): %s tracked, %s rejected by Matomo, %s skipped",
            len(events),
            result.get("tracked"),
            result.get("rejected"),
            result.get("skipped"),
        )
        return True


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


class Shipper:
    def __init__(
        self,
        reader,
        state,
        client,
        batch_size=100,
        flush_interval=5.0,
        max_backoff=300.0,
        default_scheme="http",
    ):
        self.reader = reader
        self.state = state
        self.client = client
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_backoff = max_backoff
        self.default_scheme = default_scheme
        self.stopping = threading.Event()

    def stop(self, *args):
        self.stopping.set()

    def collect(self):
        """Collect lines until the batch is full or the flush interval ends.

        Returns the lines, and the inode and offset just after them.
        """
        lines = []
        deadline = None
        while not self.stopping.is_set():
            new_lines = self.reader.read_lines(self.batch_size - len(lines))
            if new_lines:
                lines.extend(new_lines)
                deadline = deadline or time.monotonic() + self.flush_interval
            if len(lines) >= self.batch_size:
                break
            if lines and time.monotonic() >= deadline:
                break
            if not new_lines:
                self.stopping.wait(0.2)
        return lines, self.reader.inode, self.reader.offset

    def ship(self, lines):
        """Send lines until they are accepted, return False when stopping."""
        events = []
        for line in lines:
            event = to_event(line.decode("utf-8", "replace"), self.default_scheme)
            if event is None:
                logger.warning("Skipping unreadable log line: %r", line[:200])
            else:
                events.append(event)
        if not events:
            return True
        delay = min(1.0, self.max_backoff)
        while not self.client.send(events):
            if self.stopping.wait(delay):
                return False
            delay = min(delay * 2, self.max_backoff)
        return True

    def run_once(self):
        """Ship one batch, return True when there was something to ship."""
        lines, inode, offset = self.collect()
        if not lines:
            return False
        if self.ship(lines):
            self.state.save(inode, offset)
        return True

    def run(self):
        logger.info("Shipping %s to %s", self.reader.path, self.client.url)
        while not self.stopping.is_set():
            self.run_once()


def main(argv=None):
    environ = os.environ
    parser = ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--log-file",
        default=environ.get("MATOMO_AI_LOG_FILE", "/var/log/varnish/ai-bots.log"),
    )
    parser.add_argument(
        "--state-file",
        default=environ.get(
            "MATOMO_AI_STATE_FILE", "/var/lib/matomo-ai-shipper/state.json"
        ),
    )
    parser.add_argument(
        "--plone-url",
        default=environ.get("MATOMO_AI_PLONE_URL"),
        help="URL of the Plone site, preferably not through Varnish",
    )
    parser.add_argument("--username", default=environ.get("MATOMO_AI_USERNAME"))
    parser.add_argument(
        "--password-file",
        default=environ.get("MATOMO_AI_PASSWORD_FILE"),
        help="file with the password, or set MATOMO_AI_PASSWORD",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--flush-interval", type=float, default=5.0)
    parser.add_argument("--max-backoff", type=float, default=300.0)
    parser.add_argument(
        "--default-scheme",
        default="http",
        choices=("http", "https"),
        help="scheme for requests without X-Forwarded-Proto",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    password = environ.get("MATOMO_AI_PASSWORD")
    if args.password_file:
        password = Path(args.password_file).read_text().strip()
    if not args.plone_url or not args.username or not password:
        parser.error("--plone-url, --username and a password are required")

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    state = State(args.state_file)
    shipper = Shipper(
        LogReader(args.log_file, *state.load()),
        state,
        PloneClient(args.plone_url, args.username, password),
        batch_size=args.batch_size,
        flush_interval=args.flush_interval,
        max_backoff=args.max_backoff,
        default_scheme=args.default_scheme,
    )
    signal.signal(signal.SIGTERM, shipper.stop)
    signal.signal(signal.SIGINT, shipper.stop)
    shipper.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
