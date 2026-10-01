"""교보문고 상품 상세 수집 클라이언트.

교보문고는 공개 Open API를 제공하지 않는다. 확인한 사실은 다음과 같다.
- 상세 URL을 바로 열면 본문이 비어 있다(응답 크기 0).
- 검색 페이지를 먼저 열어 세션 쿠키를 받고 Referer를 붙이면 상세 HTML이 온다.
- 상세 HTML은 `<h1 aria-label="본표제">`와 바로 뒤의 `<p aria-label="부제 | 판형">`에
  본표제와 부제를 나눠 두고 있다.

따라서 알라딘 API와 국중도 상세 페이지에서 부제를 얻지 못했을 때만 쓰는
마지막 보완 수단이다. 화면 구조가 바뀌면 부제만 비고 나머지 조회는 그대로다.
"""

import logging
import re
from html import unescape
from typing import Any

import httpx

logger = logging.getLogger(__name__)

KYOBO_SEARCH_URL = "https://search.kyobobook.co.kr/search"
KYOBO_PRODUCT_URL_RE = re.compile(r"https://product\.kyobobook\.co\.kr/detail/[A-Z0-9]+")
_TITLE_HEADING_RE = re.compile(r'<h1[^>]*aria-label="([^"]*)"[^>]*>(.*?)</h1>(.*?)(?:</div>|<h2)', re.S)
_PARAGRAPH_LABEL_RE = re.compile(r'<p[^>]*aria-label="([^"]*)"', re.S)
SOURCE_NAME = "kyobobook.co.kr"
# 교보 상세는 브라우저 세션을 전제로 하므로 일반 브라우저 UA로 요청한다.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def extract_title_and_subtitle(html_text: str) -> tuple[str, str]:
    """상세 HTML에서 본표제와 부제를 뽑는다. 없으면 빈 문자열."""

    match = _TITLE_HEADING_RE.search(html_text)
    if match is None:
        return "", ""

    title = unescape(match.group(1)).strip()
    paragraph = _PARAGRAPH_LABEL_RE.search(match.group(3))
    if paragraph is None:
        return title, ""

    # aria-label은 '부제 | 양장본 Hardcover'처럼 판형을 덧붙인다. 첫 조각만 부제다.
    subtitle = unescape(paragraph.group(1)).split("|")[0].strip()
    if not subtitle or subtitle == title:
        return title, ""
    return title, subtitle


async def fetch_kyobo_detail(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """검색 → 상세 두 단계로 교보문고 상품 상세를 가져온다."""

    try:
        search = await client.get(
            KYOBO_SEARCH_URL, params={"keyword": isbn}, headers=_BROWSER_HEADERS, timeout=10
        )
        search.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("교보 검색 HTTP 오류: isbn=%s status=%s", isbn, exc.response.status_code)
        return {"source": SOURCE_NAME, "found": False, "error": f"HTTP {exc.response.status_code}"}
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("교보 검색 호출 실패: isbn=%s error_type=%s", isbn, type(exc).__name__)
        return {"source": SOURCE_NAME, "found": False, "error": "upstream request failed"}

    product_url = KYOBO_PRODUCT_URL_RE.search(search.text)
    if product_url is None:
        return {"source": SOURCE_NAME, "found": False, "title": "", "subtitle": ""}

    try:
        detail = await client.get(
            product_url.group(0),
            headers={**_BROWSER_HEADERS, "Referer": "https://search.kyobobook.co.kr/"},
            timeout=10,
        )
        detail.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("교보 상세 HTTP 오류: isbn=%s status=%s", isbn, exc.response.status_code)
        return {"source": SOURCE_NAME, "found": False, "error": f"HTTP {exc.response.status_code}"}
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("교보 상세 호출 실패: isbn=%s error_type=%s", isbn, type(exc).__name__)
        return {"source": SOURCE_NAME, "found": False, "error": "upstream request failed"}

    title, subtitle = extract_title_and_subtitle(detail.text)
    if not title:
        return {"source": SOURCE_NAME, "found": False, "title": "", "subtitle": ""}
    return {
        "source": SOURCE_NAME,
        "found": True,
        "product_url": product_url.group(0),
        "title": title,
        "subtitle": subtitle,
    }
