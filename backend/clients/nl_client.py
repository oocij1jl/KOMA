import logging
import re
from html import unescape
from typing import Any

import httpx

try:  # pragma: no cover - import path depends on startup context
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from config import settings


logger = logging.getLogger(__name__)

NL_SEOJI_URL = "https://www.nl.go.kr/seoji/SearchApi.do"
# ISBN 서지정보 API(SearchApi.do) 출력 항목에는 부서명(부제) 필드가 없다.
# 같은 기관의 ISBN/CIP 상세 페이지는 본표제와 부제를 이어 붙인 표제사항을
# 보여주므로, 부제는 이 페이지에서만 확보할 수 있다.
NL_SEOJI_DETAIL_URL = "https://nl.go.kr/seoji/contents/S80100000000.do"
_SEOJI_TITLE_BLOCK_RE = re.compile(r'<div class="tit">\s*<b class="themeFC">(.*?)</div>', re.S)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_LEADING_MEDIA_LABEL_RE = re.compile(r"^\s*\[[^\]]*\]\s*")


def _extract_seoji_title_statement(html_text: str) -> str:
    """상세 페이지에서 '[종이책] 본표제 - 부제' 머리글의 표제사항만 뽑는다."""

    match = _SEOJI_TITLE_BLOCK_RE.search(html_text)
    if match is None:
        return ""
    text = _HTML_TAG_RE.sub("", _HTML_COMMENT_RE.sub("", match.group(1)))
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return _LEADING_MEDIA_LABEL_RE.sub("", text).strip()


async def fetch_nl_seoji_title_statement(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """국중도 ISBN/CIP 상세 페이지의 표제사항을 가져온다.

    API가 아니라 공개 웹 페이지이므로 값을 해석하지 않고 화면 문자열만 돌려준다.
    부제 분리는 API 본표제와 대조해 lookup 단계에서 한다. 실패해도 조회 전체를
    막지 않도록 오류를 결과로 돌려준다.
    """

    try:
        resp = await client.get(
            NL_SEOJI_DETAIL_URL,
            params={"schM": "intgr_detail_view_isbn", "isbn": isbn},
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("국중도 상세 페이지 HTTP 오류: isbn=%s status=%s", isbn, exc.response.status_code)
        return {"source": "nl.go.kr/seoji-detail", "found": False, "error": f"HTTP {exc.response.status_code}"}
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("국중도 상세 페이지 호출 실패: isbn=%s error_type=%s", isbn, type(exc).__name__)
        return {"source": "nl.go.kr/seoji-detail", "found": False, "error": "upstream request failed"}

    statement = _extract_seoji_title_statement(resp.text)
    if not statement:
        return {"source": "nl.go.kr/seoji-detail", "found": False, "title_statement": ""}
    return {"source": "nl.go.kr/seoji-detail", "found": True, "title_statement": statement}


def _strip_price(raw: str) -> str:
    """가격 정규화: 콤마·통화기호 제거 후 숫자만 → '₩' 접두."""
    if not raw:
        return ""
    digits = re.sub(r"[^\d]", "", raw)
    return f"₩{digits}" if digits else ""


async def fetch_nl_isbn(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """국중도 ISBN 서지정보 API → 정규화 dict."""
    if not settings.NL_API_KEY:
        logger.warning("NL_API_KEY 미설정으로 국중도 조회 불가")
        return {"source": "nl.go.kr", "error": "API 키 미설정 (NL_API_KEY)"}

    params = {
        "cert_key": settings.NL_API_KEY,
        "result_style": "json",
        "page_no": 1,
        "page_size": 1,
        "isbn": isbn,
    }
    try:
        resp = await client.get(NL_SEOJI_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("국중도 API HTTP 오류: isbn=%s status=%s", isbn, exc.response.status_code)
        return {"source": "nl.go.kr", "error": f"HTTP {exc.response.status_code}"}
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("국중도 API 호출 실패: isbn=%s error_type=%s", isbn, type(exc).__name__)
        return {"source": "nl.go.kr", "error": "upstream request failed"}

    docs = data.get("docs", [])
    if not docs:
        return {"source": "nl.go.kr", "found": False}

    raw = docs[0]
    return {
        "source": "nl.go.kr",
        "found": True,
        "title": raw.get("TITLE", ""),
        "author": raw.get("AUTHOR", ""),
        "publisher": raw.get("PUBLISHER", ""),
        "publish_predate": raw.get("PUBLISH_PREDATE", ""),
        "isbn": raw.get("EA_ISBN", ""),
        "isbn_add_code": raw.get("EA_ADD_CODE", ""),
        "set_isbn": raw.get("SET_ISBN", ""),
        "set_add_code": raw.get("SET_ADD_CODE", ""),
        "set_expression": raw.get("SET_EXPRESSION", ""),
        "price": _strip_price(raw.get("PRE_PRICE", "")),
        "edition_stmt": raw.get("EDITION_STMT", ""),
        "series_title": raw.get("SERIES_TITLE", ""),
        "series_no": raw.get("SERIES_NO", ""),
        "volume": raw.get("VOL", ""),
        "page": raw.get("PAGE", ""),
        "book_size": raw.get("BOOK_SIZE", ""),
        "form": raw.get("FORM", ""),
        "kdc": raw.get("KDC", ""),
        "ddc": raw.get("DDC", ""),
        "subject": raw.get("SUBJECT", ""),
        "ebook_yn": raw.get("EBOOK_YN", ""),
        "cip_yn": raw.get("CIP_YN", ""),
        "control_no": raw.get("CONTROL_NO", ""),
        "cover_url": raw.get("TITLE_URL", ""),
        "toc_url": raw.get("BOOK_TB_CNT_URL", ""),
        "intro_url": raw.get("BOOK_INTRODUCTION_URL", ""),
    }
