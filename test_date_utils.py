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


class CommaSeparatedDateTests(unittest.TestCase):
    def test_expand_korean_abbreviated_day_list(self):
        text = "(미확정) 항공우주기술 STAR 멘토링 8월 5일, 12, 14, 20, 24, 27일 중 3일"

        expanded, changed = date_utils.expand_comma_separated_dates(text)

        self.assertTrue(changed)
        self.assertIn("8월 5일, 8월 12일, 8월 14일, 8월 20일, 8월 24일, 8월 27일", expanded)
        self.assertIn("중 3일", expanded)
        self.assertEqual(
            date_utils.extract_comma_separated_date_lists(text),
            [(None, 8, [5, 12, 14, 20, 24, 27])],
        )

    def test_expand_is_idempotent_after_full_dates(self):
        text = "멘토링 8월 5일, 8월 12일, 8월 14일"

        expanded, changed = date_utils.expand_comma_separated_dates(text)

        self.assertFalse(changed)
        self.assertEqual(expanded, text)

    def test_normalize_injects_discrete_date_rule(self):
        text = "스터디 8월 5일, 12, 14일"

        normalized = date_utils.normalize_date_ranges(text)

        self.assertTrue(normalized.startswith("[중요 일정 해석 규칙]"))
        self.assertIn("8월 5일, 8월 12일, 8월 14일", normalized)

    def test_expand_numeric_day_list(self):
        text = "회의 8/5, 12, 14"

        expanded, changed = date_utils.expand_comma_separated_dates(text)

        self.assertTrue(changed)
        self.assertIn("8월 5일, 8월 12일, 8월 14일", expanded)

    def test_align_events_when_ai_returns_single_range(self):
        source = "(미확정) 항공우주기술 STAR 멘토링 8월 5일, 12, 14, 20, 24, 27일 중 3일"
        events = [
            {
                "title": "(미확정) 항공우주기술 STAR 멘토링",
                "start_date": "20260805T090000",
                "end_date": "20260827T180000",
                "location": "",
                "details": "후보 일정",
                "details_brief": "후보 일정",
            }
        ]

        aligned = date_utils.align_events_to_listed_dates(events, source)

        self.assertEqual(len(aligned), 6)
        self.assertEqual(
            [e["start_date"][:8] for e in aligned],
            ["20260805", "20260812", "20260814", "20260820", "20260824", "20260827"],
        )
        self.assertTrue(all(e["title"] == events[0]["title"] for e in aligned))

    def test_align_keeps_correct_event_count(self):
        source = "멘토링 8월 5일, 12, 14일"
        events = [
            {
                "title": "멘토링",
                "start_date": f"202608{day:02d}T090000",
                "end_date": f"202608{day:02d}T180000",
                "location": "",
                "details": "",
                "details_brief": "",
            }
            for day in (5, 12, 14)
        ]

        aligned = date_utils.align_events_to_listed_dates(events, source)

        self.assertEqual(len(aligned), 3)
        self.assertEqual(aligned, events)

    def test_range_tilde_is_not_treated_as_comma_list(self):
        text = "교육 8월 5일~7일"

        expanded, changed = date_utils.expand_comma_separated_dates(text)

        self.assertFalse(changed)
        self.assertEqual(expanded, text)
        self.assertEqual(date_utils.extract_comma_separated_date_lists(text), [])


class SanitizeLocationTests(unittest.TestCase):
    def test_clears_org_name_for_online_recruitment(self):
        source = (
            "서울AI허브 입주기업 모집\n"
            "모집기간: 2026-07-01 ~ 2026-07-31\n"
            "모집방법: 온라인 접수\n"
            "문의: 02-1234-5678"
        )
        events = [
            {
                "title": "서울AI허브 입주기업 모집",
                "start_date": "20260731T090000",
                "end_date": "20260731T180000",
                "location": "서울AI허브",
                "details": "모집방법: 온라인 접수\n문의: 02-1234-5678",
                "details_brief": "모집방법: 온라인 접수",
            }
        ]

        cleaned = date_utils.sanitize_event_locations(events, source)

        self.assertEqual(cleaned[0]["location"], "")
        self.assertEqual(cleaned[0]["title"], events[0]["title"])
        self.assertIn("온라인 접수", cleaned[0]["details"])

    def test_clears_ai_hub_variant_location(self):
        source = "서울 ai 허브 입주기업모집\n모집방법:온라인접수"
        events = [
            {
                "title": "서울AI허브 입주기업모집",
                "start_date": "20260731T090000",
                "end_date": "20260731T180000",
                "location": "AI허브",
                "details": "모집방법: 온라인접수",
                "details_brief": "온라인접수",
            }
        ]

        cleaned = date_utils.sanitize_event_locations(events, source)

        self.assertEqual(cleaned[0]["location"], "")

    def test_clears_online_as_location_label(self):
        events = [
            {
                "title": "스타트업 모집",
                "start_date": "20260731T090000",
                "end_date": "20260731T180000",
                "location": "온라인",
                "details": "모집방법: 온라인 신청",
                "details_brief": "온라인 신청",
            }
        ]

        cleaned = date_utils.sanitize_event_locations(events, "")

        self.assertEqual(cleaned[0]["location"], "")

    def test_keeps_real_venue_when_present(self):
        source = (
            "세브란스병원 진료\n"
            "장소: 세브란스병원 본관 3층\n"
            "주소: 서울특별시 서대문구 연세로 50-1"
        )
        events = [
            {
                "title": "세브란스병원 진료",
                "start_date": "20260801T100000",
                "end_date": "20260801T110000",
                "location": "서울특별시 서대문구 연세로 50-1 세브란스병원 본관 3층",
                "details": "진료 예약",
                "details_brief": "본관 3층",
            }
        ]

        cleaned = date_utils.sanitize_event_locations(events, source)

        self.assertEqual(
            cleaned[0]["location"],
            "서울특별시 서대문구 연세로 50-1 세브란스병원 본관 3층",
        )

    def test_keeps_venue_even_if_online_also_mentioned(self):
        source = (
            "설명회 안내\n"
            "모집방법: 온라인 접수\n"
            "개최장소: 서울시청 시민홀\n"
            "8월 10일 14시"
        )
        events = [
            {
                "title": "설명회",
                "start_date": "20260810T140000",
                "end_date": "20260810T160000",
                "location": "서울시청 시민홀",
                "details": "모집방법: 온라인 접수 / 개최장소: 서울시청 시민홀",
                "details_brief": "서울시청 시민홀",
            }
        ]

        cleaned = date_utils.sanitize_event_locations(events, source)

        self.assertEqual(cleaned[0]["location"], "서울시청 시민홀")


class ApplyAnnouncementUrlTests(unittest.TestCase):
    def test_online_announcement_uses_url_as_location(self):
        source = "https://notice.example/apply\n모집방법: 온라인 접수\n신청 마감: 2026-08-19"
        events = [
            {
                "title": "지원사업 모집마감",
                "start_date": "20260819T180000",
                "end_date": "20260819T180000",
                "location": "",
                "details": "모집방법: 온라인 접수",
                "details_brief": "온라인 접수",
            }
        ]

        updated = date_utils.apply_announcement_url(events, source)

        self.assertEqual(updated[0]["location"], "https://notice.example/apply")
        self.assertEqual(updated[0]["details"], "모집방법: 온라인 접수")

    def test_offline_event_keeps_venue_and_puts_url_in_details(self):
        source = "설명회 https://notice.example/offline\n장소: 서울시청 시민홀"
        events = [
            {
                "title": "창업 설명회",
                "start_date": "20260820T140000",
                "end_date": "20260820T160000",
                "location": "서울시청 시민홀",
                "details": "참석자 안내",
                "details_brief": "시민홀 설명회",
            }
        ]

        updated = date_utils.apply_announcement_url(events, source)

        self.assertEqual(updated[0]["location"], "서울시청 시민홀")
        self.assertIn("https://notice.example/offline", updated[0]["details"])
        self.assertIn("https://notice.example/offline", updated[0]["details_brief"])
        self.assertIn("참석자 안내", updated[0]["details"])

    def test_offline_location_mixed_with_url_is_split(self):
        source = "https://notice.example/class"
        events = [
            {
                "title": "오프라인 교육",
                "start_date": "20260820T100000",
                "end_date": "20260820T120000",
                "location": "강남 코엑스 3층 https://notice.example/class",
                "details": "준비물 안내",
                "details_brief": "코엑스 교육",
            }
        ]

        updated = date_utils.apply_announcement_url(events, source)

        self.assertEqual(updated[0]["location"], "강남 코엑스 3층")
        self.assertIn("공고: https://notice.example/class", updated[0]["details"])

    def test_does_not_duplicate_url_already_in_details(self):
        source = "https://notice.example/keep"
        events = [
            {
                "title": "오프라인 교육",
                "start_date": "20260820T100000",
                "end_date": "20260820T120000",
                "location": "서울시 강남구 영동대로 513 코엑스",
                "details": "공고: https://notice.example/keep\n준비물 안내",
                "details_brief": "공고: https://notice.example/keep",
            }
        ]

        updated = date_utils.apply_announcement_url(events, source)

        self.assertEqual(updated[0]["details"].count("https://notice.example/keep"), 1)
        self.assertEqual(updated[0]["details_brief"].count("https://notice.example/keep"), 1)

    def test_leaves_events_unchanged_without_url(self):
        events = [
            {
                "title": "내부 회의",
                "start_date": "20260820T100000",
                "end_date": "20260820T110000",
                "location": "본관 3층",
                "details": "팀 회의",
                "details_brief": "팀 회의",
            }
        ]

        updated = date_utils.apply_announcement_url(events, "내일 본관 3층에서 회의")

        self.assertEqual(updated[0]["location"], "본관 3층")
        self.assertEqual(updated[0]["details"], "팀 회의")

    def test_prefers_fetched_page_url_over_body_links(self):
        source = (
            "웹페이지 원본 URL: https://notice.example/official\n"
            "본문 링크 https://other.example/unrelated"
        )
        events = [
            {
                "title": "온라인 모집",
                "start_date": "20260819T180000",
                "end_date": "20260819T180000",
                "location": "",
                "details": "온라인 접수",
                "details_brief": "온라인 접수",
            }
        ]

        updated = date_utils.apply_announcement_url(events, source)

        self.assertEqual(updated[0]["location"], "https://notice.example/official")


def public_endpoint():
    return (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        ("93.184.216.34", 80),
    )


if __name__ == "__main__":
    unittest.main()
