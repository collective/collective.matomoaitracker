from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from shipper.matomo_ai_shipper import LogReader
from shipper.matomo_ai_shipper import PloneClient
from shipper.matomo_ai_shipper import Shipper
from shipper.matomo_ai_shipper import State
from shipper.matomo_ai_shipper import to_event
from threading import Thread

import json
import os
import pytest
import time


def log_line(url="/page", **overrides):
    """A line as varnishncsa writes it with varnishncsa/ai-bots.format."""
    values = {
        "time": "1791100000",
        "client_ip": "10.0.0.2",
        "forwarded_for": "192.0.2.10, 10.0.0.1",
        "proto": "https",
        "host": "www.example.org",
        "url": url,
        "status": "200",
        "bytes": "1234",
        "content_type": "application/pdf",
        "duration_us": "12345",
        "handling": "hit",
        "category": "user",
        "user_agent": "Claude-User/1.0",
        "referrer": "",
    }
    values.update(overrides)
    return json.dumps(values) + "\n"


class TestToEvent:
    def test_full_line(self):
        assert to_event(log_line("/page?q=1")) == {
            "time": 1791100000,
            "url": "https://www.example.org/page?q=1",
            "user_agent": "Claude-User/1.0",
            "ip": "192.0.2.10",
            "status": 200,
            "bytes": 1234,
            "duration_ms": 12,
            "cache": "hit",
            "content_type": "application/pdf",
        }

    def test_missing_headers(self):
        event = to_event(
            log_line(
                forwarded_for="",
                proto="",
                bytes="-",
                content_type="",
                referrer="https://a.b/",
            )
        )

        assert event is not None
        assert event["url"] == "http://www.example.org/page"
        assert event["ip"] == "10.0.0.2"
        assert event["referrer"] == "https://a.b/"
        assert "bytes" not in event
        assert "content_type" not in event

    def test_default_scheme(self):
        event = to_event(log_line(proto=""), default_scheme="https")

        assert event is not None
        assert event["url"].startswith("https://")

    @pytest.mark.parametrize(
        "line",
        [
            "not json",
            "[]",
            log_line(host=""),
            log_line(url="http://other.example/"),
            log_line(time="yesterday"),
        ],
    )
    def test_unusable_lines(self, line):
        assert to_event(line) is None


class TestLogReader:
    def test_reads_complete_lines_only(self, tmp_path):
        log = tmp_path / "ai-bots.log"
        log.write_text("one\ntwo\nthr")
        reader = LogReader(log)

        assert reader.read_lines(10) == [b"one\n", b"two\n"]
        assert reader.offset == 8

        with log.open("a") as f:
            f.write("ee\n")
        assert reader.read_lines(10) == [b"three\n"]

    def test_limit(self, tmp_path):
        log = tmp_path / "ai-bots.log"
        log.write_text("one\ntwo\nthree\n")
        reader = LogReader(log)

        assert reader.read_lines(2) == [b"one\n", b"two\n"]
        assert reader.read_lines(2) == [b"three\n"]

    def test_continues_at_saved_position(self, tmp_path):
        log = tmp_path / "ai-bots.log"
        log.write_text("one\ntwo\n")
        reader = LogReader(log, log.stat().st_ino, 4)

        assert reader.read_lines(10) == [b"two\n"]

    def test_waits_for_the_file(self, tmp_path):
        log = tmp_path / "ai-bots.log"
        reader = LogReader(log)

        assert reader.read_lines(10) == []
        log.write_text("one\n")
        assert reader.read_lines(10) == [b"one\n"]

    def test_follows_rotation(self, tmp_path):
        log = tmp_path / "ai-bots.log"
        log.write_text("one\n")
        reader = LogReader(log)
        assert reader.read_lines(10) == [b"one\n"]

        # Written after reading, before varnishncsa reopens its file.
        with log.open("a") as f:
            f.write("two\n")
        log.rename(tmp_path / "ai-bots.log.1")
        log.write_text("three\n")

        assert reader.read_lines(10) == [b"two\n"]
        assert reader.read_lines(10) == []
        assert reader.read_lines(10) == [b"three\n"]
        assert reader.inode == log.stat().st_ino

    def test_saved_position_in_rotated_file(self, tmp_path):
        log = tmp_path / "ai-bots.log"
        log.write_text("one\ntwo\n")
        inode = log.stat().st_ino
        log.rename(tmp_path / "ai-bots.log.1")
        log.write_text("three\n")

        reader = LogReader(log, inode, 4)

        assert reader.read_lines(10) == [b"two\n"]
        assert reader.read_lines(10) == []
        assert reader.read_lines(10) == [b"three\n"]

    def test_follows_copytruncate(self, tmp_path):
        log = tmp_path / "ai-bots.log"
        log.write_text("one\ntwo\n")
        reader = LogReader(log)
        assert len(reader.read_lines(10)) == 2

        log.write_text("x\n")

        assert reader.read_lines(10) == [b"x\n"]


class TestState:
    def test_save_and_load(self, tmp_path):
        state = State(tmp_path / "state.json")

        assert state.load() == (None, 0)
        state.save(12, 34)
        assert state.load() == (12, 34)
        assert os.listdir(tmp_path) == ["state.json"]


class FakePlone:
    """The @@matomoaitracker view on a random local port."""

    def __init__(self):
        self.received = []
        self.statuses = []
        self.headers = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                fake.headers.append(dict(self.headers))
                status = fake.statuses.pop(0) if fake.statuses else 200
                if status == 200:
                    events = json.loads(body)["events"]
                    fake.received.append(events)
                    payload = {"tracked": len(events), "rejected": 0, "skipped": 0}
                elif status == 302:
                    payload = {}
                else:
                    payload = {"error": "test"}
                data = json.dumps(payload).encode()
                self.send_response(status)
                if status == 302:
                    self.send_header("Location", "/require_login")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format, *args):  # noqa: A002 - as in the base class
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/Plone"
        Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def plone():
    fake = FakePlone()
    yield fake
    fake.stop()


class TestPloneClient:
    def test_sends_events_with_basic_auth(self, plone):
        client = PloneClient(plone.url, "shipper", "secret")

        assert client.send([{"time": 1}]) is True
        assert plone.received == [[{"time": 1}]]
        assert plone.headers[0]["Authorization"] == "Basic c2hpcHBlcjpzZWNyZXQ="

    @pytest.mark.parametrize("status", [302, 401, 403, 500, 502, 503])
    def test_retries(self, plone, status):
        plone.statuses = [status]

        assert PloneClient(plone.url, "shipper", "secret").send([{}]) is False
        assert plone.received == []

    @pytest.mark.parametrize("status", [400, 413])
    def test_drops_batches_that_can_never_succeed(self, plone, status):
        plone.statuses = [status]

        assert PloneClient(plone.url, "shipper", "secret").send([{}]) is True

    def test_unreachable(self, plone):
        plone.stop()

        assert PloneClient(plone.url, "shipper", "secret").send([{}]) is False


class TestShipper:
    def make_shipper(self, tmp_path, plone, batch_size=2):
        log = tmp_path / "ai-bots.log"
        state = State(tmp_path / "state.json")
        shipper = Shipper(
            LogReader(log, *state.load()),
            state,
            PloneClient(plone.url, "shipper", "secret"),
            batch_size=batch_size,
            flush_interval=0,
            max_backoff=0.01,
        )
        return log, state, shipper

    def test_ships_batches_and_saves_the_position(self, tmp_path, plone):
        log, state, shipper = self.make_shipper(tmp_path, plone)
        log.write_text(log_line("/1") + log_line("/2") + "garbage\n" + log_line("/3"))

        assert shipper.run_once() is True
        assert shipper.run_once() is True

        urls = [event["url"] for batch in plone.received for event in batch]
        assert urls == [
            "https://www.example.org/1",
            "https://www.example.org/2",
            "https://www.example.org/3",
        ]
        assert state.load() == (log.stat().st_ino, log.stat().st_size)

    def test_retries_until_plone_accepts(self, tmp_path, plone):
        log, state, shipper = self.make_shipper(tmp_path, plone)
        log.write_text(log_line("/1"))
        plone.statuses = [503, 502, 401]

        assert shipper.run_once() is True

        assert len(plone.headers) == 4
        assert len(plone.received) == 1
        assert state.load()[1] == log.stat().st_size

    def test_continues_after_restart(self, tmp_path, plone):
        log, _state, shipper = self.make_shipper(tmp_path, plone)
        log.write_text(log_line("/1"))
        shipper.run_once()

        with log.open("a") as f:
            f.write(log_line("/2"))
        _log, _state, restarted = self.make_shipper(tmp_path, plone)
        restarted.run_once()

        assert [batch[0]["url"] for batch in plone.received] == [
            "https://www.example.org/1",
            "https://www.example.org/2",
        ]

    def test_position_is_kept_when_stopped_during_an_outage(self, tmp_path, plone):
        log, state, shipper = self.make_shipper(tmp_path, plone)
        log.write_text(log_line("/1"))
        plone.stop()
        running = Thread(target=shipper.run_once)
        running.start()

        time.sleep(0.5)
        assert running.is_alive(), "the shipper should keep retrying"
        shipper.stop()
        running.join(5)

        assert not running.is_alive()
        assert state.load() == (None, 0)
