from collective.matomoaitracker.browser.tracking import MatomoVarnishLogConsumerView
from json import dumps
from json import loads
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch


class TestMatomoVarnishLogConsumerView(TestCase):
    def make_view(self, payload, method="POST"):
        request = Mock()
        request.method = method
        request.get.return_value = dumps(payload)
        request.response = Mock()
        return MatomoVarnishLogConsumerView(None, request)

    def test_tracks_each_event_with_its_original_user_agent(self):
        events = [
            {"url": "https://example.org/page", "user_agent": "GPTBot/1.0"},
            {"url": "https://example.org/other", "user_agent": "ClaudeBot/1.0"},
        ]
        view = self.make_view({"events": events})

        with patch.object(
            MatomoVarnishLogConsumerView, "_track", return_value=True
        ) as track:
            result = loads(view())

        self.assertEqual(result, {"results": [True, True]})
        track.assert_any_call("https://example.org/page", "GPTBot/1.0")
        track.assert_any_call("https://example.org/other", "ClaudeBot/1.0")

    def test_rejects_invalid_event_without_tracking_partial_batch(self):
        events = [
            {"url": "https://example.org/page", "user_agent": "GPTBot/1.0"},
            {"url": "javascript:alert(1)", "user_agent": "GPTBot/1.0"},
        ]
        view = self.make_view({"events": events})

        with patch.object(MatomoVarnishLogConsumerView, "_track") as track:
            result = loads(view())

        self.assertEqual(result, {"error": "Invalid event"})
        view.request.response.setStatus.assert_called_once_with(400)
        track.assert_not_called()

    def test_requires_post(self):
        view = self.make_view({"events": []}, method="GET")

        with patch.object(MatomoVarnishLogConsumerView, "_track") as track:
            result = loads(view())

        self.assertEqual(result, {"error": "POST required"})
        view.request.response.setStatus.assert_called_once_with(405)
        track.assert_not_called()
