from collective.matomoaitracker.browser.tracking import MatomoAIChatbotTrackingView
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch


class TestMatomoAIChatbotTrackingView(TestCase):
    def make_view(self, url="https://example.org/page", user_agent="GPTBot/1.0"):
        request = Mock()
        request.form = {"url": url}
        request.getHeader.return_value = user_agent
        request.response = Mock()
        return MatomoAIChatbotTrackingView(None, request)

    def test_tracks_synchronously_before_returning_no_content(self):
        view = self.make_view()

        with patch.object(MatomoAIChatbotTrackingView, "_track") as track:
            result = view()

        track.assert_called_once_with("https://example.org/page", "GPTBot/1.0")
        view.request.response.setStatus.assert_called_once_with(204)
        view.request.response.setHeader.assert_called_once_with(
            "Cache-Control", "no-store"
        )
        self.assertEqual(result, "")

    def test_skips_tracking_when_request_data_is_missing(self):
        for url, user_agent in (("", "GPTBot/1.0"), ("https://example.org", "")):
            with self.subTest(url=url, user_agent=user_agent):
                view = self.make_view(url=url, user_agent=user_agent)

                with patch.object(MatomoAIChatbotTrackingView, "_track") as track:
                    view()

                track.assert_not_called()
                view.request.response.setStatus.assert_called_once_with(204)
