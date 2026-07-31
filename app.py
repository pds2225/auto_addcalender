import base64
import json
import os
import re
import subprocess
import urllib.parse
from datetime import datetime, timedelta

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI

from clipboard_paste import clipboard_paste_zone
from date_utils import (
    align_events_to_listed_dates,
    dedupe_event_titles,
    normalize_date_ranges,
)

st.set_page_config(page_title="Omni-Sync Mobile", layout="centered")
st.title("📅 AI 일정 자동 등록")


def get_build_version():
    # Streamlit Cloud/GitHub 배포 환경에서 커밋 SHA를 우선 사용
    for key in ["GITHUB_SHA", "COMMIT_SHA", "RENDER_GIT_COMMIT"]:
        if os.getenv(key):
            return os.getenv(key)[:7]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


BUILD_VERSION = get_build_version()
st.caption(f"빌드 버전: {BUILD_VERSION}")

# 배포 버전이 바뀌면 URL 쿼리 버전을 맞춰 자동 새로고침(수동 clear cache/rerun 최소화)
try:
    query_version = st.query_params.get("v")
    if query_version != BUILD_VERSION:
        st.query_params["v"] = BUILD_VERSION
        st.rerun()
except Exception:
    pass

api_key = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=api_key)

KO_DAYS = ["월", "화", "수", "목", "금", "토", "일"]
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
CLIPBOARD_PASTE_KEY = "clipboard_paste_input"

EVENT_EXTRACTION_RULES = """
[출력 형식]
{
  "events": [
    {
      "title": "구체적인 일정 제목",
      "start_date": "YYYYMMDDTHHMMSS",
      "end_date": "YYYYMMDDTHHMMSS",
      "location": "전체 장소 또는 주소",
      "details": "참석자 필요 정보 전체",
      "details_brief": "핵심 요약 (180자 이내)"
    }
  ]
}

[제목 규칙]
- 제목은 캘린더 목록에서 일정 내용을 바로 구분할 수 있게 구체적으로 작성
- 기관명, 병원명, 회사명, 장소명, 진료과, 상담/진료/교육/회의 등 일정 성격을 함께 보존
- 단순 동작만 남기지 말 것 (예: "진료", "회의", "교육"만 단독 사용 금지)
- 연도(2026년 등), 차수(제7차, 제3회 등), 기수(1기, 2기 등)는 제목 식별에 필요 없을 때만 제거
- 여러 일정을 추출할 때는 서로 다른 일정에 동일한 제목을 절대 사용하지 말 것 — 차수·회차·세션명·과목명 등 구분 정보를 제목에 유지해 제목만 봐도 각 일정이 구분되게 작성
- 예: "세브란스병원 진료 예약" → "세브란스병원 진료"
- 예: "2026년 제7차 희망리턴패키지 재도전교육" → "희망리턴패키지 재도전교육"

[날짜 규칙]
- 기간 표기(예: 2026-05-01~2026-05-03)는 1개의 이벤트로 생성
- 쉼표·공백으로 날짜만 나열된 경우(예: 8월 5일, 12, 14, 20일)는 각 날짜마다 별도 이벤트 생성. 기간 하나로 묶지 말 것. '중 N일' 등 후보 표현이 있어도 나열된 모든 날짜를 각각 등록
- 마감일, 모집 종료, 신청 마감, 접수 마감, 기한, 지원 마감 등 기한을 의미하는 경우 마지막 날짜에만 1개의 이벤트 생성 (start_date와 end_date 모두 마지막 날짜로 설정)
- start_date: 시작일의 도착시간 또는 첫 세션 시작시간
- end_date: 마지막 날짜의 마지막 세션 종료시간 또는 퇴실시간
- 도착/퇴실 시간이 명시된 경우 그 시간을 사용
- 시간이 전혀 없는 경우 start=09:00, end=18:00으로 설정

[장소 규칙]
- location에는 원문에 나온 주소, 기관명, 건물명, 층, 호실을 최대한 함께 포함
- 주소가 있으면 주소를 반드시 포함 (예: "서울시 서대문구 ... 세브란스병원 본관 3층")
- 기관명만 있고 주소가 없으면 기관명과 세부 위치(층/호실/강의실)를 포함
- 장소 정보가 여러 줄로 나뉘어 있어도 하나의 location 문자열로 합쳐서 작성

[details 규칙]
- 참석자에게 필요한 모든 정보를 원문 그대로 빠짐없이 포함할 것
- 포함: 세션·과목·시간표, 전체 장소/주소(건물명·층·호실 포함), 준비물, 유의사항, 문의처, 연락처, 전화번호, 이메일, 신청 방법, 지참 서류 등
- 문의처, 연락처, 전화번호, 이메일이 원문에 있으면 details에 반드시 포함
- 제외: 기관 소개·홍보 문구·행사 취지 설명 등 참석자 행동과 무관한 내용
- 내용을 요약하거나 임의로 생략하지 말 것

[details_brief 규칙]
- details 내용을 180자 이내로 압축 요약
- 우선순위: ① 전체 장소/주소 ② 문의처·연락처·전화번호·이메일 ③ 준비물·지참 서류 ④ 주요 세션명·일정 흐름
- 문의처, 연락처, 전화번호, 이메일이 원문에 있으면 details_brief에도 가능한 한 포함
- 한 줄 또는 글머리표 2~3개 이내로 작성
- 구글 캘린더 메모란에 표시될 요약본

[날짜 형식]
- 반드시 YYYYMMDDTHHMMSS 형식만 사용
- ISO 8601 금지
- JSON 외 텍스트 절대 출력 금지
"""

# ── 세션 초기화 ────────────────────────────────────────
for key, default in {
    "input_text": "",
    "events": [],
    "registered": False,
    "pasted_image_data_url": None,
    "image_source": None,
    "image_bytes": None,
    "image_mime": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── 유틸 함수 ──────────────────────────────────────────
def validate_gcal_date(date_str):
    return bool(re.match(r"^\d{8}T\d{6}$", str(date_str)))


def fmt(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y%m%dT%H%M%S")
        day_ko = KO_DAYS[dt.weekday()]
        return dt.strftime(f"%m/%d({day_ko}) %H:%M")
    except Exception:
        return date_str


def parse_data_url_image(data_url):
    if not data_url or "," not in data_url:
        raise ValueError("잘못된 이미지 데이터입니다.")

    header, encoded = data_url.split(",", 1)
    if not header.startswith("data:") or ";base64" not in header:
        raise ValueError("지원하지 않는 이미지 형식입니다.")

    mime_type = header[5:].split(";")[0]
    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("지원하지 않는 이미지 형식입니다. PNG, JPG, WEBP, GIF만 사용할 수 있습니다.")

    image_bytes = base64.b64decode(encoded)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("이미지 크기는 10MB 이하여야 합니다.")

    return image_bytes, mime_type


def get_image_input():
    image_bytes = st.session_state.get("image_bytes")
    image_mime = st.session_state.get("image_mime")
    if image_bytes:
        return image_bytes, image_mime or "image/jpeg"

    uploaded_file = st.session_state.get("uploaded_image")
    if uploaded_file is not None:
        return uploaded_file.getvalue(), uploaded_file.type or "image/jpeg"

    pasted_data_url = st.session_state.get("pasted_image_data_url")
    if pasted_data_url:
        return parse_data_url_image(pasted_data_url)

    return None, None


def clear_image_input():
    st.session_state.pasted_image_data_url = None
    st.session_state.image_source = None
    st.session_state.image_bytes = None
    st.session_state.image_mime = None


def clear_image_input_callback():
    clear_image_input()
    st.session_state.uploaded_image = None
    if CLIPBOARD_PASTE_KEY in st.session_state:
        del st.session_state[CLIPBOARD_PASTE_KEY]


def sync_uploaded_image(uploaded_file):
    st.session_state.image_bytes = uploaded_file.getvalue()
    st.session_state.image_mime = uploaded_file.type or "image/jpeg"
    st.session_state.image_source = "upload"
    st.session_state.pasted_image_data_url = None


def apply_pasted_image(data_url):
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        return False
    try:
        image_bytes, mime_type = parse_data_url_image(data_url)
    except ValueError:
        return False

    st.session_state.pasted_image_data_url = data_url
    st.session_state.image_bytes = image_bytes
    st.session_state.image_mime = mime_type
    st.session_state.image_source = "paste"
    return True


def get_preview_image():
    image_source = st.session_state.get("image_source")
    uploaded_file = st.session_state.get("uploaded_image")
    pasted_data_url = st.session_state.get("pasted_image_data_url")

    if image_source == "upload" and uploaded_file is not None:
        return uploaded_file, "선택한 이미지"
    if image_source == "paste" and pasted_data_url:
        return pasted_data_url, "붙여넣은 이미지"
    if uploaded_file is not None:
        return uploaded_file, "선택한 이미지"
    if pasted_data_url:
        return pasted_data_url, "붙여넣은 이미지"
    return None, None


def validate_extracted_events(events, source_label="입력"):
    if not events:
        raise ValueError(f"일정을 추출하지 못했습니다. {source_label}을(를) 다시 확인해 주세요.")

    for i, event in enumerate(events):
        if not validate_gcal_date(event.get("start_date", "")):
            raise ValueError(f"이벤트 {i+1} start_date 형식 오류: {event.get('start_date')}")
        if not validate_gcal_date(event.get("end_date", "")):
            raise ValueError(f"이벤트 {i+1} end_date 형식 오류: {event.get('end_date')}")

    return events


def process_text(text):
    normalized_text = normalize_date_ranges(text)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt = f"""
현재 시간은 {current_time} (KST) 입니다.

아래 안내문에서 일정을 추출하여 JSON 배열로만 출력하십시오.
{EVENT_EXTRACTION_RULES}
텍스트:
{normalized_text}
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    data = json.loads(response.choices[0].message.content)
    return validate_extracted_events(data.get("events", []), "텍스트")


def process_image(image_bytes, mime_type, supplemental_text=""):
    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("지원하지 않는 이미지 형식입니다. PNG, JPG, WEBP, GIF만 사용할 수 있습니다.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("이미지 크기는 10MB 이하여야 합니다.")

    normalized_text = normalize_date_ranges(supplemental_text) if supplemental_text.strip() else ""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_lines = ["아래 이미지에서 일정을 추출하여 JSON 배열로만 출력하십시오."]
    if normalized_text:
        source_lines.extend(
            [
                "이미지와 함께 제공된 추가 텍스트도 함께 참고하십시오.",
                "추가 텍스트:",
                normalized_text,
            ]
        )

    prompt = f"""
현재 시간은 {current_time} (KST) 입니다.

{chr(10).join(source_lines)}
{EVENT_EXTRACTION_RULES}
"""
    image_data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    data = json.loads(response.choices[0].message.content)
    return validate_extracted_events(data.get("events", []), "이미지")


def build_calendar_url(event):
    # Use brief summary for URL to avoid Google Calendar 400 error from long URLs.
    # Korean chars encode to ~9x length, so details_brief (≤100 chars) stays safe.
    # /r/eventedit + calid=primary: forces "내 캘린더" on mobile (avoids "메모" calendar default).
    details = event.get('details_brief') or event.get('details', '')
    if len(details) > 200:
        details = details[:200] + '...'
    return (
        "https://calendar.google.com/calendar/render"
        "?action=TEMPLATE"
        "&src=primary"
        f"&text={urllib.parse.quote(event.get('title', '새 일정'), safe='')}"
        f"&dates={event['start_date']}/{event['end_date']}"
        "&ctz=Asia%2FSeoul"
        f"&location={urllib.parse.quote(event.get('location', ''), safe='')}"
        f"&details={urllib.parse.quote(details, safe='')}"
    )


def split_multiday_events(events):
    result = []
    for event in events:
        try:
            start = datetime.strptime(event['start_date'], "%Y%m%dT%H%M%S")
            end = datetime.strptime(event['end_date'], "%Y%m%dT%H%M%S")
        except (ValueError, KeyError):
            result.append(event)
            continue
        if start.date() == end.date():
            result.append(event)
            continue
        start_t = start.strftime("%H%M%S")
        end_t = end.strftime("%H%M%S")
        base_title = str(event.get('title', '')).strip()
        current = start.date()
        day_num = 1
        while current <= end.date():
            day_event = dict(event)
            if base_title:
                # 날짜별로 쪼갠 일정이 캘린더에서 같은 제목으로 보이지 않게 일차 표기
                day_event['title'] = f"{base_title} ({day_num}일차)"
            day_event['start_date'] = f"{current.strftime('%Y%m%d')}T{start_t}"
            day_event['end_date'] = f"{current.strftime('%Y%m%d')}T{end_t}"
            result.append(day_event)
            current += timedelta(days=1)
            day_num += 1
    return result


def escape_ics_text(value):
    if not value:
        return ""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def build_ics_content(event):
    return build_ics_calendar_content([event])


def build_ics_calendar_content(events):
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//OmniSync//AutoCalendar//KO\n"
        "CALSCALE:GREGORIAN\n"
    ]
    for event in events:
        uid = f"{event.get('start_date', '')}-{abs(hash(event.get('title', 'event')))}@omni-sync"
        title = escape_ics_text(event.get("title", "새 일정"))
        details = escape_ics_text(event.get("details", ""))
        location = escape_ics_text(event.get("location", ""))
        lines.extend(
            [
                "BEGIN:VEVENT\n",
                f"UID:{uid}\n",
                f"DTSTAMP:{now_utc}\n",
                f"DTSTART;TZID=Asia/Seoul:{event['start_date']}\n",
                f"DTEND;TZID=Asia/Seoul:{event['end_date']}\n",
                f"SUMMARY:{title}\n",
                f"DESCRIPTION:{details}\n",
                f"LOCATION:{location}\n",
                "END:VEVENT\n",
            ]
        )
    lines.append("END:VCALENDAR\n")
    return "".join(lines)


def make_ics_filename(title, index=None):
    base = re.sub(r"[^\w가-힣-]+", "_", str(title or "calendar").strip(), flags=re.UNICODE)
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        base = "calendar"
    base = base[:40].strip("_") or "calendar"
    if index is not None:
        return f"{index:02d}_{base}.ics"
    return f"{base}.ics"


def render_bulk_register_section(events, selected_platforms):
    """선택한 일정의 구글 등록 화면을 한 번에 연다."""
    if len(events) < 2 or "구글 캘린더" not in selected_platforms:
        return

    st.subheader("⚡ 일괄 등록")

    bulk_options = {
        i: f"{event.get('title', '새 일정')} · {fmt(event['start_date'])}"
        for i, event in enumerate(events)
    }
    selected_indices = st.multiselect(
        "일괄 열기할 일정",
        options=list(bulk_options.keys()),
        default=list(bulk_options.keys()),
        format_func=lambda idx: bulk_options[idx],
        key="bulk_register_indices",
        help="이미 개별 등록한 일정은 체크를 해제하세요.",
    )
    selected_events = [events[i] for i in selected_indices]
    count = len(selected_events)
    urls_json = json.dumps(
        [build_calendar_url(event) for event in selected_events],
        ensure_ascii=False,
    )
    disabled_attr = "disabled" if count == 0 else ""

    bulk_open_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    padding: 2px 0;
  }}
  button {{
    width: 100%;
    background: #1a73e8;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 12px 14px;
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
  }}
  button:disabled {{
    background: #9aa0a6;
    cursor: not-allowed;
  }}
  #bulk-msg {{
    margin-top: 8px;
    font-size: 12px;
    color: #5f6368;
    line-height: 1.5;
  }}
</style>
</head>
<body>
<button {disabled_attr} onclick="openAllGoogle()">구글 일괄 열기 ({count}개)</button>
<p id="bulk-msg">팝업이 막히면 브라우저에서 팝업을 허용한 뒤 다시 눌러 주세요.</p>
<script>
var urls = {urls_json};
function openAllGoogle() {{
  var msg = document.getElementById('bulk-msg');
  if (!urls.length) {{
    msg.textContent = '열 일정을 선택해 주세요.';
    return;
  }}
  var opened = 0;
  urls.forEach(function(url) {{
    var win = window.open(url, '_blank');
    if (win) opened += 1;
  }});
  if (opened === 0) {{
    msg.textContent = '팝업이 차단되었습니다. 팝업을 허용한 뒤 다시 눌러 주세요.';
  }} else if (opened < urls.length) {{
    msg.textContent = opened + '개만 열렸습니다. 팝업을 허용하면 나머지도 열립니다.';
  }} else {{
    msg.textContent = opened + '개 등록 화면을 열었습니다.';
  }}
}}
</script>
</body>
</html>
"""
    components.html(bulk_open_html, height=88)


def render_event_cards(events, selected_platforms):
    for i, event in enumerate(events):
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f"**{event.get('title', '')}**")
                st.markdown(f"📅 &nbsp;{fmt(event['start_date'])} ~ {fmt(event['end_date'])}")
                if event.get("location"):
                    st.markdown(f"📍 &nbsp;{event['location']}")
                if event.get("details"):
                    with st.expander("📝 메모"):
                        st.text(event["details"])
            with right:
                if "구글 캘린더" in selected_platforms:
                    st.link_button(
                        "구글 등록",
                        build_calendar_url(event),
                        use_container_width=True,
                    )
                if "카카오 캘린더(.ics)" in selected_platforms:
                    st.download_button(
                        "카카오 등록(.ics)",
                        data=build_ics_content(event),
                        file_name=make_ics_filename(event.get("title", ""), i + 1),
                        mime="text/calendar",
                        use_container_width=True,
                    )


def clear_all():
    st.session_state.input_text = ""
    clear_image_input_callback()
    st.session_state.events = []
    st.session_state.registered = False


# ══════════════════════════════════════════════════════
# 입력 영역
# ══════════════════════════════════════════════════════
user_input = st.text_area(
    "일정 내용을 입력하세요",
    key="input_text",
    placeholder="복사한 텍스트를 붙여넣거나, 아래에서 이미지를 첨부하세요.",
)

st.caption("이미지는 **파일 선택** 또는 **클립보드 붙여넣기(Ctrl+V)** 로 추가할 수 있습니다.")

uploaded_image = st.file_uploader(
    "이미지 파일 선택 (선택)",
    type=["png", "jpg", "jpeg", "webp", "gif"],
    key="uploaded_image",
    help="포스터, 초대장, 스크린샷 등에서 일정을 추출합니다.",
)

pasted_data_url = clipboard_paste_zone(
    label="여기를 클릭한 뒤 Ctrl+V(⌘+V)로 붙여넣거나, 이미지 파일을 끌어다 놓으세요.",
    key=CLIPBOARD_PASTE_KEY,
)

if uploaded_image is not None:
    sync_uploaded_image(uploaded_image)
elif apply_pasted_image(pasted_data_url):
    pass

preview_image, preview_caption = get_preview_image()

if preview_image is not None:
    source_label = "파일 첨부" if st.session_state.get("image_source") == "upload" else "붙여넣기"
    st.success(f"✅ 이미지 준비됨 ({source_label})")
    st.image(preview_image, caption=preview_caption, use_container_width=True)
    st.button("이미지 지우기", key="clear_image_input", on_click=clear_image_input_callback)

if st.button("일정등록", use_container_width=True):
    has_text = bool(user_input.strip())
    image_bytes, image_mime = get_image_input()
    has_image = image_bytes is not None

    if has_text or has_image:
        with st.spinner("AI 분석 중..."):
            try:
                if has_image:
                    events = process_image(image_bytes, image_mime, user_input)
                else:
                    events = process_text(user_input)
                st.session_state.events = split_multiday_events(
                    dedupe_event_titles(
                        align_events_to_listed_dates(events, user_input)
                    )
                )
                st.session_state.registered = True
            except Exception as e:
                st.error("처리 중 오류가 발생했습니다. 입력 내용을 다시 확인해 주세요.")
                st.write(e)
    else:
        st.warning("텍스트 또는 이미지를 입력해 주세요.")


# ══════════════════════════════════════════════════════
# 등록 결과 영역
# ══════════════════════════════════════════════════════
if st.session_state.registered and st.session_state.events:
    events = st.session_state.events

    st.markdown("---")
    st.success(f"✅ {len(events)}개 일정 등록 완료!")
    selected_platforms = st.multiselect(
        "등록할 캘린더를 선택하세요",
        options=["구글 캘린더", "카카오 캘린더(.ics)"],
        default=["구글 캘린더"],
        help="카카오는 .ics 파일 다운로드 후 카카오 캘린더에서 가져오기로 등록할 수 있습니다.",
    )
    st.caption("여러 일정이면 위에서 구글 일괄 열기를 사용하세요.")

    # ── 일괄 등록 ─────────────────────────────────────
    render_bulk_register_section(events, selected_platforms)

    # ── 등록된 일정 카드 ──────────────────────────────
    if len(events) >= 2:
        st.markdown("##### 일정별 개별 등록")
    render_event_cards(events, selected_platforms)

    # ── 공유 영역 (완전 클라이언트 사이드) ───────────────
    st.markdown("---")
    st.subheader("📤 공유하기")
    st.info(
        "카카오톡에는 일정 내용 텍스트를 먼저 공유하세요.\n"
        "캘린더 등록이 필요한 사람에게는 아래 .ics 파일도 함께 전달하면 됩니다.\n"
        "받는 사람은 .ics 파일을 열어 카카오 캘린더 또는 휴대폰 캘린더에 직접 저장할 수 있습니다.\n"
        "이미 등록한 일정을 다시 가져오면 중복 등록될 수 있으니, 새로 공유할 일정만 선택해 다운로드하세요."
    )

    share_options = {
        i: f"{event.get('title', '새 일정')} · {fmt(event['start_date'])}"
        for i, event in enumerate(events)
    }
    selected_share_indices = st.multiselect(
        "공유할 일정을 선택하세요",
        options=list(share_options.keys()),
        default=list(share_options.keys()),
        format_func=lambda idx: share_options[idx],
    )
    selected_share_events = [events[i] for i in selected_share_indices]

    st.download_button(
        "선택한 일정만 .ics 다운로드",
        data=build_ics_calendar_content(selected_share_events),
        file_name="selected_calendar_events.ics",
        mime="text/calendar",
        use_container_width=True,
        disabled=not selected_share_events,
        help="체크한 일정만 하나의 .ics 파일로 내려받습니다.",
    )

    # 공유용 이벤트 데이터: 메모와 연도는 제외하고 다운로드 전 확인 가능한 핵심 정보만 포함
    share_events = json.dumps(
        [
            {
                "title": e.get("title", ""),
                "date": f"{fmt(e['start_date'])} ~ {fmt(e['end_date'])}",
                "location": e.get("location", ""),
            }
            for e in selected_share_events
        ],
        ensure_ascii=False,
    )

    component_height = 80 + len(selected_share_events) * 64 + 100

    share_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 4px 2px; }}
  .item {{
    display: flex; align-items: center;
    padding: 10px 6px; border-bottom: 1px solid #eee;
  }}
  .item input[type=checkbox] {{
    width: 20px; height: 20px; margin-right: 12px;
    cursor: pointer; flex-shrink: 0; accent-color: #4285F4;
  }}
  .item label {{ font-size: 14px; line-height: 1.5; cursor: pointer; }}
  .item label .sub {{ font-size: 12px; color: #888; }}
  .kakao-btn {{
    display: block; width: 100%; margin-top: 14px;
    background: #FEE500; color: #3C1E1E;
    padding: 14px; border: none; border-radius: 8px;
    font-size: 16px; font-weight: bold; cursor: pointer;
    letter-spacing: -0.3px;
  }}
  #msg {{
    margin-top: 10px; font-size: 13px; color: #555;
    white-space: pre-wrap; line-height: 1.6;
  }}
</style>
</head>
<body>
<div id="list"></div>
<button class="kakao-btn" onclick="doShare()">💬 카카오톡 공유하기 (실패 시 자동 복사)</button>
<p id="msg"></p>
<script>
var events = {share_events};

var list = document.getElementById('list');
events.forEach(function(e, i) {{
  var div = document.createElement('div');
  div.className = 'item';
  div.innerHTML =
    '<input type="checkbox" id="c' + i + '" checked>' +
    '<label for="c' + i + '">' + e.title +
    '<br><span class="sub">' + e.date +
    (e.location ? ' · ' + e.location : '') +
    '</span></label>';
  list.appendChild(div);
}});

async function doShare() {{
  var lines = [];
  var hasSelected = false;
  events.forEach(function(e, i) {{
    if (document.getElementById('c' + i).checked) {{
      if (hasSelected) lines.push('');
      hasSelected = true;
      lines.push('[' + e.title + ']');
      lines.push('일시: ' + e.date);
      if (e.location) lines.push('장소: ' + e.location);
    }}
  }});

  if (!hasSelected) {{
    document.getElementById('msg').textContent = '⚠️ 공유할 일정을 선택해 주세요.';
    return;
  }}

  var text = lines.join('\\n');
  var msg = document.getElementById('msg');

  async function copyToClipboard(value) {{
    try {{
      if (navigator.clipboard && window.isSecureContext) {{
        await navigator.clipboard.writeText(value);
      }} else {{
        var ta = document.createElement('textarea');
        ta.value = value;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }}
      msg.textContent = '✅ 복사 완료!\\n카카오톡을 열고 붙여넣기 하세요.';
      return true;
    }} catch (copyErr) {{
      msg.textContent = '아래 내용을 직접 복사하세요:\\n\\n' + value;
      return false;
    }}
  }}

  // 모바일 공유가 불안정한 환경(웹뷰/브라우저 정책) 대비: canShare로 선검증
  var canNativeShare = false;
  try {{
    canNativeShare =
      !!navigator.share &&
      (!navigator.canShare || navigator.canShare({{ title: '일정 공유', text: text }}));
  }} catch (e) {{
    canNativeShare = false;
  }}

  if (canNativeShare) {{
    try {{
      await navigator.share({{ title: '일정 공유', text: text }});
      msg.textContent = '✅ 공유되었습니다.';
      return;
    }} catch (shareErr) {{
      if (shareErr && shareErr.name === 'AbortError') {{
        msg.textContent = '공유가 취소되어 복사 모드로 전환합니다.';
      }} else {{
        msg.textContent = '공유 실패로 복사 모드로 전환합니다.';
      }}
    }}
  }}

  await copyToClipboard(text);
}}
</script>
</body>
</html>
"""

    components.html(share_html, height=component_height)

    st.markdown("---")
    st.button("새 일정 입력", on_click=clear_all, use_container_width=True)
