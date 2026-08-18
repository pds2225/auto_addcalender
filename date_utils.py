import html
import http.client
import ipaddress
import re
import socket
import urllib.parse
from calendar import monthrange
from datetime import datetime
from html.parser import HTMLParser


MAX_WEBPAGE_BYTES = 2 * 1024 * 1024
MAX_EXTRACTED_TEXT = 40000
MAX_REDIRECTS = 5
URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
# Zoom/Meet 등 입장 링크는 웹페이지가 아니라 일정 장소로 취급한다.
_MEETING_HOSTS = (
    "zoom.us",
    "meet.google.com",
    "teams.microsoft.com",
    "teams.live.com",
    "webex.com",
    "gotomeeting.com",
    "whereby.com",
)
DEADLINE_PATTERN = re.compile(
    r"접수\s*마감|신청\s*마감|모집\s*마감|지원\s*마감|제출\s*마감|"
    r"접수\s*종료|신청\s*종료|모집\s*종료|마감일|신청\s*기한|제출\s*기한",
    re.IGNORECASE,
)
ONLINE_METHOD_PATTERN = re.compile(
    r"(?:모집|접수|신청|지원)\s*방법\s*[:：]?\s*온라인|"
    r"온라인\s*(?:접수|신청|지원|등록)|"
    r"비대면\s*(?:접수|신청|지원)",
    re.IGNORECASE,
)
VENUE_MARKER_PATTERN = re.compile(
    r"(?:개최|행사|교육|설명회|면접)\s*장소|"
    r"(?<![가-힣])장소\s*[:：]|주소\s*[:：]|오시는\s*길|"
    r"\d+\s*층|[A-Za-z]?\d+\s*호실?|강의실|회의실|"
    r"(?:서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|"
    r"울산광역시|세종특별자치시|경기도|강원특별자치도|충청북도|충청남도|"
    r"전북특별자치도|전라북도|전라남도|경상북도|경상남도|제주특별자치도|"
    r"서울시|부산시|대구시|인천시|광주시|대전시|울산시)\s*\S+",
    re.IGNORECASE,
)
ONLINE_ONLY_LOCATION_PATTERN = re.compile(
    r"^(?:온라인|비대면|온라인\s*접수|온라인\s*신청|온라인\s*지원)$",
    re.IGNORECASE,
)
PHYSICAL_VENUE_PATTERN = re.compile(
    r"[가-힣0-9A-Za-z]+(?:홀|센터|호텔|병원|학교|대학교|캠퍼스|빌딩|타워|"
    r"구청|시청|박물관|미술관|공원|스테이션|회관|극장|복지관|플라자)|"
    r"[가-힣]+(?:로|길|동|가)\s*\d+",
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


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_public_url(url: str):
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
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("올바른 웹페이지 포트가 아닙니다.") from exc

    try:
        results = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("웹페이지 주소를 찾을 수 없습니다.") from exc

    endpoints = []
    seen = set()
    for family, socktype, proto, _, sockaddr in results:
        if not _is_public_address(sockaddr[0]):
            raise ValueError("내부 또는 비공개 네트워크 주소는 열 수 없습니다.")
        endpoint_key = (family, socktype, proto, sockaddr)
        if endpoint_key not in seen:
            endpoints.append((family, socktype, proto, sockaddr))
            seen.add(endpoint_key)

    if not endpoints:
        raise ValueError("웹페이지 주소를 찾을 수 없습니다.")

    return parsed, hostname, port, endpoints


def _validate_public_url(url: str) -> str:
    _resolve_public_url(url)
    return url


def _connect_to_endpoint(endpoint, timeout, source_address=None):
    family, socktype, proto, sockaddr = endpoint
    sock = socket.socket(family, socktype, proto)
    try:
        sock.settimeout(timeout)
        if source_address:
            sock.bind(source_address)
        sock.connect(sockaddr)
        return sock
    except Exception:
        sock.close()
        raise


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Connect to the exact address returned by the URL safety check."""

    def __init__(self, host, port, endpoint, timeout):
        super().__init__(host, port=port, timeout=timeout)
        self._endpoint = endpoint

    def connect(self):
        self.sock = _connect_to_endpoint(
            self._endpoint,
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Pin the TCP peer while retaining the hostname for TLS verification."""

    def __init__(self, host, port, endpoint, timeout):
        super().__init__(host, port=port, timeout=timeout)
        self._endpoint = endpoint

    def connect(self):
        self.sock = _connect_to_endpoint(
            self._endpoint,
            self.timeout,
            self.source_address,
        )
        server_hostname = self.host
        if self._tunnel_host:
            self._tunnel()
            server_hostname = self._tunnel_host
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=server_hostname,
        )


def _host_header(hostname: str, port: int, scheme: str) -> str:
    host = hostname.encode("idna").decode("ascii")
    if ":" in host:
        host = f"[{host}]"
    default_port = 443 if scheme == "https" else 80
    return host if port == default_port else f"{host}:{port}"


def _request_target(parsed) -> str:
    path = urllib.parse.quote(
        parsed.path or "/",
        safe="/%:@!$&'()*+,;=-._~",
    )
    if not parsed.query:
        return path
    query = urllib.parse.quote(
        parsed.query,
        safe="=&?/:@!$'()*+,;%-._~",
    )
    return f"{path}?{query}"


def _open_pinned_response(parsed, hostname, port, endpoints):
    headers = {
        "Host": _host_header(hostname, port, parsed.scheme),
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/126 Safari/537.36 OmniSync/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        "Connection": "close",
    }
    connection_type = (
        _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
    )
    last_error = None

    for endpoint in endpoints:
        connection = connection_type(
            hostname,
            port,
            endpoint,
            timeout=12,
        )
        try:
            connection.request(
                "GET",
                _request_target(parsed),
                headers=headers,
            )
            return connection, connection.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
            connection.close()

    raise ValueError("웹페이지 연결에 실패했습니다.") from last_error


def _read_webpage(url: str):
    current_url = url

    for redirect_count in range(MAX_REDIRECTS + 1):
        parsed, hostname, port, endpoints = _resolve_public_url(current_url)
        connection = None
        try:
            connection, response = _open_pinned_response(
                parsed,
                hostname,
                port,
                endpoints,
            )
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("웹페이지 이동 주소가 없습니다.")
                if redirect_count >= MAX_REDIRECTS:
                    raise ValueError("웹페이지 이동 횟수가 너무 많습니다.")
                current_url = urllib.parse.urljoin(current_url, location)
                continue

            if response.status >= 400:
                raise ValueError(f"웹페이지를 열 수 없습니다. HTTP {response.status}")

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
            return current_url, content_type, decoded
        except (OSError, http.client.HTTPException) as exc:
            raise ValueError("웹페이지 연결에 실패했습니다.") from exc
        finally:
            if connection is not None:
                connection.close()

    raise ValueError("웹페이지 이동 횟수가 너무 많습니다.")


def fetch_webpage_text(url: str) -> str:
    final_url, content_type, decoded = _read_webpage(url)

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


def _url_hostname(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_meeting_url(url: str) -> bool:
    """Zoom/Meet 등 입장 링크인지 여부. 공고 페이지 주소와 구분한다."""
    host = _url_hostname(url)
    if not host:
        return False
    for meeting_host in _MEETING_HOSTS:
        if host == meeting_host or host.endswith("." + meeting_host):
            return True
    return False


def _extract_urls(text: str):
    urls = []
    seen = set()
    for match in URL_PATTERN.finditer(text or ""):
        url = match.group(0).rstrip(".,);]}")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def extract_meeting_urls(text: str):
    """입력 텍스트에서 Zoom/Meet 등 입장 링크만 순서대로 반환한다."""
    return [url for url in _extract_urls(text) if _is_meeting_url(url)]


def expand_url_input(text: str) -> str:
    """입력에 URL이 있으면 첫 번째 공개 웹페이지를 읽고 나머지 입력 문구와 합친다.

    Zoom/Meet 입장 링크는 페이지를 가져오지 않는다. 일정의 장소로 남겨 둔다.
    """
    for match in URL_PATTERN.finditer(text or ""):
        url = match.group(0).rstrip(".,);]}")
        if _is_meeting_url(url):
            continue
        supplemental = (text[: match.start()] + text[match.end() :]).strip()
        try:
            page_text = fetch_webpage_text(url)
        except ValueError:
            if supplemental:
                return text
            raise
        if supplemental:
            return f"{page_text}\n\n사용자 추가 입력:\n{supplemental}"
        return page_text
    return text


def _is_deadline_focused(text: str) -> bool:
    """Limit the single-deadline rule to a primary title or explicit user instruction."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return False

    candidates = []
    page_titles = [
        line.split(":", 1)[1].strip()
        for line in lines
        if line.startswith("페이지 제목:") and ":" in line
    ]
    if page_titles:
        candidates.extend(page_titles)
    else:
        first_line = next(
            (
                line
                for line in lines
                if not line.startswith("웹페이지 원본 URL:")
                and line != "사용자 추가 입력:"
            ),
            "",
        )
        if first_line:
            candidates.append(first_line)

    for index, line in enumerate(lines):
        if line == "사용자 추가 입력:" and index + 1 < len(lines):
            candidates.append(lines[index + 1])

    return any(DEADLINE_PATTERN.search(candidate) for candidate in candidates)


# 나열 항목의 일(day): "12일" 또는 "12" (뒤에 월/년/추가 자릿수가 오면 제외)
# → 이미 펼쳐진 "8월 5일, 8월 12일" 이 다시 매칭되지 않게 함
_DAY_LIST_ITEM = r"(?:\d{1,2}\s*일|\d{1,2}(?!\s*[월년])(?![-./\d]))"

# 예: "8월 5일, 12, 14, 20, 24, 27일" / "2026년 8월 5일, 12일, 14일"
_KOREAN_COMMA_DATE_LIST = re.compile(
    r"(?:(?P<year>\d{4})\s*년\s*)?"
    r"(?P<month>\d{1,2})\s*월\s*"
    r"(?P<head>\d{1,2})\s*일?"
    r"(?P<tail>(?:\s*[,，、]\s*" + _DAY_LIST_ITEM + r")+)"
)

# 예: "8/5, 12, 14, 20" / "2026-8-5, 12, 14"
_NUMERIC_COMMA_DATE_LIST = re.compile(
    r"(?:(?P<year>\d{4})\s*[-./]\s*)?"
    r"(?P<month>\d{1,2})\s*[-./]\s*(?P<head>\d{1,2})"
    r"(?P<tail>(?:\s*[,，、]\s*\d{1,2}(?![-./\d]))+)"
)

_DISCRETE_DATES_RULE = (
    "[중요 일정 해석 규칙]\n"
    "아래에 같은 일정의 날짜가 쉼표로 여러 개 나열되어 있습니다. "
    "나열된 각 날짜마다 별도의 이벤트를 1개씩 생성하십시오. "
    "시작~종료 기간 하나로 묶지 말고, '중 N일'처럼 후보·선택 표현이 있어도 "
    "나열된 모든 날짜를 각각 일정으로 등록하십시오. "
    "제목·장소·상세는 동일하게 유지하고 날짜만 다르게 설정하십시오.\n\n"
)
_MULTI_MEETING_RULE = (
    "[중요 일정 해석 규칙]\n"
    "아래에 온라인 교육/회의 입장 링크가 여러 개 있습니다. "
    "각 링크는 서로 다른 일정입니다. "
    "링크 개수만큼 이벤트를 각각 생성하고, "
    "각 이벤트의 location에는 해당 일정의 입장 링크만 넣으십시오. "
    "첫 번째 일정만 만들고 나머지를 합치거나 생략하지 마십시오.\n\n"
)


def _parse_days_from_chunk(chunk: str):
    days = []
    for token in re.findall(r"\d{1,2}", chunk):
        day = int(token)
        if 1 <= day <= 31:
            days.append(day)
    return days


def extract_comma_separated_date_lists(text: str):
    """쉼표로 나열된 개별 날짜 목록을 [(year|None, month, [days...]), ...] 로 반환."""
    found = []
    seen = set()

    for match in _KOREAN_COMMA_DATE_LIST.finditer(text or ""):
        month = int(match.group("month"))
        if not 1 <= month <= 12:
            continue
        days = _parse_days_from_chunk(match.group("head") + match.group("tail"))
        if len(days) < 2:
            continue
        year = int(match.group("year")) if match.group("year") else None
        key = (year, month, tuple(days))
        if key not in seen:
            seen.add(key)
            found.append((year, month, days))

    for match in _NUMERIC_COMMA_DATE_LIST.finditer(text or ""):
        month = int(match.group("month"))
        if not 1 <= month <= 12:
            continue
        days = _parse_days_from_chunk(match.group("head") + match.group("tail"))
        if len(days) < 2:
            continue
        year = int(match.group("year")) if match.group("year") else None
        key = (year, month, tuple(days))
        if key not in seen:
            seen.add(key)
            found.append((year, month, days))

    return found


def expand_comma_separated_dates(text: str):
    """축약된 날짜 나열을 각 날짜가 명시된 형태로 펼친다.

    Returns:
        (expanded_text, did_expand)
    """
    if not text:
        return text, False

    changed = False

    def repl_korean(match):
        nonlocal changed
        month = int(match.group("month"))
        if not 1 <= month <= 12:
            return match.group(0)
        days = _parse_days_from_chunk(match.group("head") + match.group("tail"))
        if len(days) < 2:
            return match.group(0)
        year = match.group("year")
        year_prefix = f"{year}년 " if year else ""
        changed = True
        return ", ".join(f"{year_prefix}{month}월 {day}일" for day in days)

    def repl_numeric(match):
        nonlocal changed
        month = int(match.group("month"))
        if not 1 <= month <= 12:
            return match.group(0)
        days = _parse_days_from_chunk(match.group("head") + match.group("tail"))
        if len(days) < 2:
            return match.group(0)
        year = match.group("year")
        if year:
            expanded = ", ".join(
                f"{int(year):04d}-{month:02d}-{day:02d}" for day in days
            )
        else:
            expanded = ", ".join(f"{month}월 {day}일" for day in days)
        changed = True
        return expanded

    expanded = _KOREAN_COMMA_DATE_LIST.sub(repl_korean, text)
    expanded = _NUMERIC_COMMA_DATE_LIST.sub(repl_numeric, expanded)
    return expanded, changed


def align_events_to_listed_dates(events, source_text: str):
    """쉼표 나열 날짜가 있는데 이벤트가 부족하거나 기간으로 묶였으면 날짜별 이벤트로 맞춘다."""
    lists = extract_comma_separated_date_lists(source_text or "")
    if len(lists) != 1:
        return events

    year, month, days = lists[0]
    if len(days) < 2:
        return events

    result_events = [dict(event) for event in (events or [])]
    if len(result_events) == len(days):
        return result_events

    template = result_events[0] if result_events else {
        "title": "새 일정",
        "location": "",
        "details": "",
        "details_brief": "",
        "start_date": f"{datetime.now().year}{month:02d}{days[0]:02d}T090000",
        "end_date": f"{datetime.now().year}{month:02d}{days[0]:02d}T180000",
    }

    start_t, end_t = "090000", "180000"
    inferred_year = year
    try:
        start = datetime.strptime(str(template.get("start_date", "")), "%Y%m%dT%H%M%S")
        end = datetime.strptime(str(template.get("end_date", "")), "%Y%m%dT%H%M%S")
        start_t = start.strftime("%H%M%S")
        end_t = end.strftime("%H%M%S")
        if inferred_year is None:
            inferred_year = start.year
    except ValueError:
        if inferred_year is None:
            inferred_year = datetime.now().year

    aligned = []
    last_day = monthrange(inferred_year, month)[1]
    for day in days:
        if day > last_day:
            continue
        event = dict(template)
        event["start_date"] = f"{inferred_year:04d}{month:02d}{day:02d}T{start_t}"
        event["end_date"] = f"{inferred_year:04d}{month:02d}{day:02d}T{end_t}"
        aligned.append(event)

    return aligned if aligned else result_events


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

    normalized, discrete_expanded = expand_comma_separated_dates(normalized)

    extra_rules = []
    if discrete_expanded:
        extra_rules.append(_DISCRETE_DATES_RULE.strip())
    elif _is_deadline_focused(normalized):
        extra_rules.append(
            "[중요 일정 해석 규칙]\n"
            "이 문서는 접수·신청·모집 등의 마감 공고입니다. "
            "접수기간 전체를 일정으로 생성하지 말고, 마감일 하루에 일정 1개만 생성하십시오. "
            "start_date와 end_date의 날짜는 모두 마감일로 설정하십시오. "
            "마감 시간이 있으면 start_date는 마감일 09:00, end_date는 명시된 마감 시간으로 설정하고, "
            "마감 시간이 없으면 마감일 09:00~18:00으로 설정하십시오."
        )
    if len(set(extract_meeting_urls(normalized))) >= 2:
        extra_rules.append(_MULTI_MEETING_RULE.strip())
    if extra_rules:
        normalized = "\n\n".join(extra_rules) + "\n\n" + normalized

    return normalized


def _start_label(event, fmt):
    try:
        return datetime.strptime(
            str(event.get("start_date", "")), "%Y%m%dT%H%M%S"
        ).strftime(fmt)
    except ValueError:
        return None


def _has_online_application_method(text: str) -> bool:
    return bool(ONLINE_METHOD_PATTERN.search(text or ""))


def _has_explicit_venue(text: str) -> bool:
    return bool(VENUE_MARKER_PATTERN.search(text or ""))


def _location_looks_like_online_method(location: str) -> bool:
    return bool(ONLINE_ONLY_LOCATION_PATTERN.match((location or "").strip()))


def _location_is_title_org_name(location: str, title: str) -> bool:
    """제목 속 기관/프로그램명만 location에 들어간 경우를 감지한다."""
    loc = re.sub(r"\s+", "", (location or "").strip())
    ttl = re.sub(r"\s+", "", (title or "").strip())
    if not loc or not ttl:
        return False
    if loc in ttl or ttl in loc:
        return True
    # "서울AI허브" vs "서울 AI 허브 입주기업 모집" 등 공백·접미사 변형
    for noise in ("입주기업모집", "입주기업", "모집", "공고", "신청", "접수", "마감"):
        ttl = ttl.replace(noise, "")
    return bool(ttl) and (loc in ttl or ttl in loc)


def sanitize_event_locations(events, source_text: str = ""):
    """온라인 접수 공고에서 기관명을 장소로 잘못 넣은 경우 location을 비운다.

    - 모집/접수 방법이 온라인이고 실제 방문 장소 표기가 없으면 location 제거
    - location이 '온라인' 등 접수방법 표현이면 제거 (details에 남김)
    원본 리스트는 수정하지 않는다.
    """
    source = source_text or ""
    online_only = _has_online_application_method(source) and not _has_explicit_venue(source)
    result = []
    for event in events or []:
        cleaned = dict(event)
        location = str(cleaned.get("location", "") or "").strip()
        title = str(cleaned.get("title", "") or "")
        details_blob = " ".join(
            [
                str(cleaned.get("details", "") or ""),
                str(cleaned.get("details_brief", "") or ""),
            ]
        )
        event_online = _has_online_application_method(details_blob)
        should_clear = False
        if location and _location_looks_like_online_method(location):
            should_clear = True
        elif location and (online_only or event_online) and not _has_explicit_venue(source):
            if _location_is_title_org_name(location, title) or online_only:
                should_clear = True
        if should_clear:
            cleaned["location"] = ""
        result.append(cleaned)
    return result


def _strip_urls(text: str) -> str:
    cleaned = URL_PATTERN.sub(" ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip(" ,;/-")


def _first_url(text: str) -> str:
    match = URL_PATTERN.search(text or "")
    if not match:
        return ""
    return match.group(0).rstrip(".,);]}")


def extract_announcement_url(text: str) -> str:
    """사용자 입력 또는 가져온 공고 페이지의 원본 URL을 반환한다.

    Zoom/Meet 입장 링크는 공고 주소가 아니므로 건너뛴다.
    """
    if not text:
        return ""
    for line in text.splitlines()[:8]:
        stripped = line.strip()
        if stripped.startswith("웹페이지 원본 URL:"):
            candidate = stripped.split(":", 1)[1].strip().rstrip(".,);]}")
            if (
                candidate
                and URL_PATTERN.match(candidate)
                and not _is_meeting_url(candidate)
            ):
                return candidate
    for url in _extract_urls(text):
        if not _is_meeting_url(url):
            return url
    return ""


def _is_physical_venue(location: str) -> bool:
    loc = _strip_urls(location)
    if not loc or ONLINE_ONLY_LOCATION_PATTERN.match(loc):
        return False
    return bool(VENUE_MARKER_PATTERN.search(loc) or PHYSICAL_VENUE_PATTERN.search(loc))


def _append_announcement_url(text: str, url: str) -> str:
    text = text or ""
    if not url or url in text:
        return text
    if text.strip():
        return f"{text.rstrip()}\n공고: {url}"
    return f"공고: {url}"


def _event_link(event) -> str:
    return _first_url(event.get("location", "") or "") or _first_url(
        event.get("details", "") or ""
    )


def apply_announcement_url(events, source_text: str = ""):
    """공고 URL이 있으면 온라인 일정은 위치, 오프라인 일정은 메모에 넣는다.

    - 실제 방문 장소가 있으면 location은 장소, 공고 링크는 details
    - 방문 장소가 없으면 location에 공고 링크를 넣는다
    - 일정마다 Zoom/Meet 링크가 다르면 첫 번째 링크로 덮어쓰지 않는다
    원본 리스트는 수정하지 않는다.
    """
    source_url = extract_announcement_url(source_text)
    meeting_urls = extract_meeting_urls(source_text)
    result_events = [dict(event) for event in (events or [])]
    event_links = [_event_link(event) for event in result_events]
    distinct_event_links = {url for url in event_links if url}
    assign_meetings_by_index = (
        len(meeting_urls) == len(result_events)
        and len(set(meeting_urls)) == len(result_events)
        and len(distinct_event_links) != len(result_events)
    )

    result = []
    for index, event in enumerate(result_events):
        cleaned = dict(event)
        location = str(cleaned.get("location", "") or "").strip()
        details = str(cleaned.get("details", "") or "")
        details_brief = str(cleaned.get("details_brief", "") or "")
        event_url = event_links[index]
        if assign_meetings_by_index:
            chosen_url = meeting_urls[index]
        elif event_url:
            chosen_url = event_url
        else:
            chosen_url = source_url or (meeting_urls[0] if len(meeting_urls) == 1 else "")
        if not chosen_url:
            result.append(cleaned)
            continue
        if _is_physical_venue(location):
            cleaned["location"] = _strip_urls(location) or location
            page_url = source_url if source_url and not _is_meeting_url(source_url) else ""
            if page_url:
                cleaned["details"] = _append_announcement_url(details, page_url)
                cleaned["details_brief"] = _append_announcement_url(
                    details_brief, page_url
                )
        else:
            cleaned["location"] = chosen_url
            if (
                source_url
                and source_url != chosen_url
                and not _is_meeting_url(source_url)
            ):
                cleaned["details"] = _append_announcement_url(details, source_url)
                cleaned["details_brief"] = _append_announcement_url(
                    details_brief, source_url
                )
        result.append(cleaned)
    return result


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
