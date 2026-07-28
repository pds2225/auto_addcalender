import socket
import unittest
from unittest.mock import Mock, patch

import date_utils


class UrlSafetyTests(unittest.TestCase):
    @patch("date_utils.socket.socket")
    @patch("date_utils.socket.getaddrinfo")
    def test_http_connection_uses_the_validated_sockaddr(self, getaddrinfo, socket_factory):
        public_endpoint = (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 80),
        )
        private_endpoint = (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("127.0.0.1", 80),
        )
        getaddrinfo.side_effect = [[public_endpoint], [private_endpoint]]
        fake_socket = Mock()
        socket_factory.return_value = fake_socket

        parsed, hostname, port, endpoints = date_utils._resolve_public_url(
            "http://rebind.example/schedule"
        )
        connection = date_utils._PinnedHTTPConnection(
            hostname,
            port,
            endpoints[0],
            timeout=12,
        )
        connection.connect()

        self.assertEqual(parsed.hostname, "rebind.example")
        self.assertEqual(getaddrinfo.call_count, 1)
        fake_socket.connect.assert_called_once_with(("93.184.216.34", 80))

    @patch("date_utils._open_pinned_response")
    @patch("date_utils._resolve_public_url")
    def test_redirect_target_is_resolved_before_following(self, resolve_url, open_response):
        first_headers = Mock()
        first_headers.get.return_value = "http://redirect.example/event"
        redirect_response = Mock(status=302, headers=first_headers)

        final_headers = Mock()
        final_headers.get_content_type.return_value = "text/plain"
        final_headers.get_content_charset.return_value = "utf-8"
        final_response = Mock(status=200, headers=final_headers)
        final_response.read.return_value = "충분히 긴 일정 안내 본문입니다. 7월 30일 오후 2시 회의입니다.".encode()

        open_response.side_effect = [
            (Mock(), redirect_response),
            (Mock(), final_response),
        ]
        resolve_url.side_effect = [
            (Mock(scheme="http"), "start.example", 80, [public_endpoint()]),
            (Mock(scheme="http"), "redirect.example", 80, [public_endpoint()]),
        ]

        final_url, content_type, _ = date_utils._read_webpage(
            "http://start.example/schedule"
        )

        self.assertEqual(final_url, "http://redirect.example/event")
        self.assertEqual(content_type, "text/plain")
        self.assertEqual(
            [call.args[0] for call in resolve_url.call_args_list],
            [
                "http://start.example/schedule",
                "http://redirect.example/event",
            ],
        )


class UrlFallbackTests(unittest.TestCase):
    @patch("date_utils.fetch_webpage_text", side_effect=ValueError("로그인 필요"))
    def test_typed_schedule_is_preserved_when_url_fetch_fails(self, _fetch):
        original = "7월 30일 14시 회의 https://zoom.us/j/12345"

        self.assertEqual(date_utils.expand_url_input(original), original)

    @patch("date_utils.fetch_webpage_text", side_effect=ValueError("로그인 필요"))
    def test_url_only_input_still_reports_extraction_failure(self, _fetch):
        with self.assertRaisesRegex(ValueError, "로그인 필요"):
            date_utils.expand_url_input("https://example.com/login-only")


class DeadlineClassificationTests(unittest.TestCase):
    def test_registration_deadline_does_not_hide_normal_event_dates(self):
        text = (
            "여름 창업 행사 안내\n"
            "행사 일시: 2026-08-05 14:00~16:00\n"
            "신청 마감: 2026-07-30 18:00"
        )

        normalized = date_utils.normalize_date_ranges(text)

        self.assertFalse(normalized.startswith("[중요 일정 해석 규칙]"))
        self.assertIn("행사 일시: 2026-08-05 14:00~16:00", normalized)

    @patch("date_utils.expand_url_input")
    def test_page_footer_deadline_does_not_override_event_title(self, expand_input):
        expand_input.return_value = (
            "웹페이지 원본 URL: https://events.example/summer\n"
            "페이지 제목: 여름 창업 행사 안내\n"
            "행사 일시: 2026-08-05 14:00~16:00\n"
            "푸터: 뉴스레터 신청 마감"
        )

        normalized = date_utils.normalize_date_ranges(
            "https://events.example/summer"
        )

        self.assertFalse(normalized.startswith("[중요 일정 해석 규칙]"))

    def test_deadline_focused_title_keeps_single_deadline_rule(self):
        text = (
            "여름 창업 행사 신청 마감 안내\n"
            "신청 마감: 2026-07-30 18:00"
        )

        normalized = date_utils.normalize_date_ranges(text)

        self.assertTrue(normalized.startswith("[중요 일정 해석 규칙]"))


def public_endpoint():
    return (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        ("93.184.216.34", 80),
    )


if __name__ == "__main__":
    unittest.main()
