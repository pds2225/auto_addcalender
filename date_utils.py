import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import datetime
from html.parser import HTMLParser


MAX_WEBPAGE_BYTES = 2 * 1024 * 1024
MAX_EXTRACTED_TEXT = 40000
URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
DEADLINE_PATTERN = re.compile(
    r"접수\s*마감|신청\s*마감|모집\s*마감|지원\s*마감|제출\s*마감|"
    r"접수\s*종료|신청\s*종료|모집\s*종료|마감일|신청\s*기한|제출\s*기한",
    re.IGNORECASE,
)


class _VisibleTextParser(HTMLParser):
    """HTML에서 제목·메타 설명·사용자에게 보이는 텍스트만 추출한다."""

    HIDDEN_TAGS = {"script", "style", "noscript", "svg", "canvas", "template"}
    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "div", "footer",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
        "main", "nav", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.in_title = False
        self.title_parts = []
        self.meta_descriptions = []
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.HIDDEN_TAGS:
            self.hidden_depth += 1
            return
        if self.hidden_depth:
            return
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            attr_map = {str(k).lower(): str(v or "") for k, v in attrs}
            key = (attr_map.get("name") or attr_map.get("property") or "").lower()
            if key in {"description", "og:description", "twitter:description"}:
                content = attr_map.get("content", "").strip()
                if content:
                    self.meta_descriptions.append(content)
        if tag in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.HIDDEN_TAGS:
            self.hidden_depth = max(0, self.hidden_depth - 1)
            return
        if self.hidden_depth:
            return
        if tag == "title":
            self.in_title = False
        if tag in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self.hidden_depth:
            return
        value = data.strip()
        if not value:
            return
        if self.in_title:
            self.title_parts.append(value)
        self.text_parts.append(value)
        self.text_parts.append(" ")

    def result(self):
        title = " ".join(self.title_parts).strip()
        description = " ".join(dict.fromkeys(self.meta_descriptions)).strip()
        body = "".join(self.text_parts)
        body = html.unescape(body)
        body = re.sub(r"[\t\r\f\v ]+", " ", body)
        body = re.sub(r"\n\s*\n+", "\n", body)
        body = body.strip()
        sections = []
        if title:
            sections.append(f"페이지 제목: {title}")
        if description:
            sections.append(f"페이지 설명: {description}")
        if body:
            sections.append(body)
        return "\n".join(sections)[:MAX_EXTRACTED_TEXT]


def _validate_public_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("http 또는 https 링크만 지원합니다.")
    if not parsed.hostname:
        raise ValueError("올바른 웹페이지 주소가 아닙니다.")
    if parsed.username or parsed.password:
        raise ValueError("사용자 인증정보가 포함된 링크는 지원하지 않습니다.")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".local"):
        raise ValueError("내부 네트워크 주소는 열 수 없습니다.")

    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise ValueError("웹페이지 주소를 찾을 수 없습니다.") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("내부 또는 비공개 네트워크 주소는 열 수 없습니다.")
    return url


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url = _validate_public_url(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def fetch_webpage_text(url: str) -> str:
    safe_url = _validate_public_url(url)
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    request = urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36 OmniSync/1.0"
            ),
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        },
    )

    try:
        with opener.open(request, timeout=12) as response:
            final_url = _validate_public_url(response.geturl())
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise ValueError(f"일정 추출을 지원하지 않는 페이지 형식입니다: {content_type}")

            raw = response.read(MAX_WEBPAGE_BYTES + 1)
            if len(raw) > MAX_WEBPAGE_BYTES:
                raise ValueError("페이지 용량이 너무 큽니다. 2MB 이하 페이지를 사용해 주세요.")

            charset = response.headers.get_content_charset() or "utf-8"
            try:
                decoded = raw.decode(charset, errors="replace")
            except LookupError:
                decoded = raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"웹페이지를 열 수 없습니다. HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError("웹페이지 연결에 실패했습니다.") from exc

    if content_type == "text/plain":
        extracted = decoded.strip()[:MAX_EXTRACTED_TEXT]
    else:
        parser = _VisibleTextParser()
        parser.feed(decoded)
        extracted = parser.result()

    if len(extracted) < 30:
        raise ValueError(
            "페이지에서 읽을 수 있는 일정 내용을 찾지 못했습니다. "
            "로그인이 필요하거나 자바스크립트로만 표시되는 페이지일 수 있습니다."
        )

    return f"웹페이지 원본 URL: {final_url}\n{extracted}"


def expand_url_input(text: str) -> str:
    """입력에 URL이 있으면 첫 번째 공개 웹페이지를 읽고 나머지 입력 문구와 합친다."""
    match = URL_PATTERN.search(text or "")
    if not match:
        return text

    url = match.group(0).rstrip(".,);]}")
    page_text = fetch_webpage_text(url)
    supplemental = (text[: match.start()] + text[match.end() :]).strip()
    if supplemental:
        return f"{page_text}\n\n사용자 추가 입력:\n{supplemental}"
    return page_text


def normalize_date_ranges(text: str) -> str:
    normalized = expand_url_input(text)

    # YYYY-MM-DD ~ DD  -> YYYY-MM-DD ~ YYYY-MM-DD
    def repl_short(match):
        year = int(match.group(1))
        month = int(match.group(2))
        start_day = int(match.group(3))
        end_day = int(match.group(4))
        last_day = monthrange(year, month)[1]
        end_day = max(1, min(end_day, last_day))
        return f"{year:04d}-{month:02d}-{start_day:02d}~{year:04d}-{month:02d}-{end_day:02d}"

    # Match only when the end number is NOT followed by a date separator (- . /)
    # Prevents "2026-05-28 ~ 06-02" from being misread as end_day=06
    normalized = re.sub(
        r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})\s*[~∼]\s*(\d{1,2})(?![-./\d])",
        repl_short,
        normalized,
    )

    if DEADLINE_PATTERN.search(normalized):
        normalized = (
            "[중요 일정 해석 규칙]\n"
            "이 문서는 접수·신청·모집 등의 마감 공고입니다. "
            "접수기간 전체를 일정으로 생성하지 말고, 마감일 하루에 일정 1개만 생성하십시오. "
            "start_date와 end_date의 날짜는 모두 마감일로 설정하십시오. "
            "마감 시간이 있으면 start_date는 마감일 09:00, end_date는 명시된 마감 시간으로 설정하고, "
            "마감 시간이 없으면 마감일 09:00~18:00으로 설정하십시오.\n\n"
            + normalized
        )

    return normalized


def _start_label(event, fmt):
    try:
        return datetime.strptime(
            str(event.get("start_date", "")), "%Y%m%dT%H%M%S"
        ).strftime(fmt)
    except ValueError:
        return None


def dedupe_event_titles(events):
    """같은 제목의 일정이 여러 개면 날짜(같으면 시간, 그래도 같으면 순번)를
    제목 뒤에 붙여 캘린더 목록에서 서로 구분되게 한다. 원본 리스트는 수정하지 않는다."""
    result = [dict(event) for event in events]

    groups = {}
    for event in result:
        groups.setdefault(str(event.get("title", "")), []).append(event)

    for title, group in groups.items():
        if len(group) < 2:
            continue
        for fmt in ("%m/%d", "%m/%d %H:%M"):
            labels = [_start_label(event, fmt) for event in group]
            if None not in labels and len(set(labels)) == len(group):
                break
        else:
            labels = [str(i + 1) for i in range(len(group))]
        for event, label in zip(group, labels):
            event["title"] = f"{title} ({label})".strip()

    return result
