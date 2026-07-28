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


def expand_url_input(text: str) -> str:
    """입력에 URL이 있으면 첫 번째 공개 웹페이지를 읽고 나머지 입력 문구와 합친다."""
    match = URL_PATTERN.search(text or "")
    if not match:
        return text

    url = match.group(0).rstrip(".,);]}")
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

    if _is_deadline_focused(normalized):
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
