"""알라딘 상품 조회 API(ItemLookUp) 클라이언트.

국중도 ISBN 서지정보 API 출력 항목에는 부제가 없다. 알라딘 상품 API는
`subInfo.subTitle`(부제), `subInfo.originalTitle`(원제), `subInfo.itemPage`(쪽수),
`subInfo.packing.sizeHeight`(세로 mm)를 제공하므로 부제와 형태사항 보완에 쓴다.

값은 해석하지 않고 그대로 옮긴다. 인증키(ALADIN_TTB_KEY)가 없으면 호출하지
않고 사유만 돌려준다. 실패해도 조회 전체를 막지 않는다.
"""

import logging
from typing import Any

import httpx

try:  # pragma: no cover - import path depends on startup context
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from config import settings


logger = logging.getLogger(__name__)

ALADIN_ITEM_LOOKUP_URL = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
ALADIN_API_VERSION = "20131101"
SOURCE_NAME = "aladin.co.kr"


def _as_text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    sub_info = item.get("subInfo") if isinstance(item.get("subInfo"), dict) else {}
    packing = sub_info.get("packing") if isinstance(sub_info.get("packing"), dict) else {}
    return {
        "source": SOURCE_NAME,
        "found": True,
        "title": _as_text(item.get("title")),
        "subtitle": _as_text(sub_info.get("subTitle")),
        "original_title": _as_text(sub_info.get("originalTitle")),
        "author": _as_text(item.get("author")),
        "publisher": _as_text(item.get("publisher")),
        "isbn13": _as_text(item.get("isbn13")),
        "description": _as_text(item.get("description")),
        "category_name": _as_text(item.get("categoryName")),
        "item_page": _as_text(sub_info.get("itemPage")),
        "size_height_mm": _as_text(packing.get("sizeHeight")),
        "size_width_mm": _as_text(packing.get("sizeWidth")),
        "packing_style": _as_text(packing.get("styleDesc")),
    }


async def fetch_aladin_item(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """알라딘 상품 조회 API → 정규화 dict."""

    if not settings.ALADIN_TTB_KEY:
        logger.info("ALADIN_TTB_KEY 미설정으로 알라딘 조회 생략")
        return {"source": SOURCE_NAME, "found": False, "error": "API 키 미설정 (ALADIN_TTB_KEY)"}

    params = {
        "ttbkey": settings.ALADIN_TTB_KEY,
        "itemIdType": "ISBN13",
        "ItemId": isbn,
        "output": "js",
        "Version": ALADIN_API_VERSION,
    }
    try:
        resp = await client.get(ALADIN_ITEM_LOOKUP_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("알라딘 API HTTP 오류: isbn=%s status=%s", isbn, exc.response.status_code)
        return {"source": SOURCE_NAME, "found": False, "error": f"HTTP {exc.response.status_code}"}
    except Exception as exc:  # pragma: no cover - network/JSON failure path
        logger.warning("알라딘 API 호출 실패: isbn=%s error_type=%s", isbn, type(exc).__name__)
        return {"source": SOURCE_NAME, "found": False, "error": "upstream request failed"}

    if not isinstance(data, dict):
        return {"source": SOURCE_NAME, "found": False, "error": "unexpected response shape"}

    error_message = _as_text(data.get("errorMessage"))
    if error_message:
        logger.warning("알라딘 API 오류 응답: isbn=%s code=%s", isbn, _as_text(data.get("errorCode")))
        return {"source": SOURCE_NAME, "found": False, "error": error_message}

    items = data.get("item")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return {"source": SOURCE_NAME, "found": False}

    return _normalize_item(items[0])
