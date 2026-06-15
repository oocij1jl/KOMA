import re
from typing import Any

import httpx

try:  # pragma: no cover - import path depends on startup context
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from config import settings


NL_SEOJI_URL = "https://www.nl.go.kr/seoji/SearchApi.do"


def _strip_price(raw: str) -> str:
    """가격 정규화: 콤마·통화기호 제거 후 숫자만 → '₩' 접두."""
    if not raw:
        return ""
    digits = re.sub(r"[^\d]", "", raw)
    return f"₩{digits}" if digits else ""


async def fetch_nl_isbn(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """국중도 ISBN 서지정보 API → 정규화 dict."""
    if not settings.NL_API_KEY:
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
        return {"source": "nl.go.kr", "error": f"HTTP {exc.response.status_code}"}
    except Exception as exc:  # pragma: no cover - network failure path
        return {"source": "nl.go.kr", "error": str(exc)}

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
