import importlib
from typing import Any

import httpx

try:  # pragma: no cover - import path depends on startup context
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    settings = importlib.import_module("config").settings


D4L_DETAIL_URL = "http://data4library.kr/api/srchDtlList"
D4L_KEYWORD_URL = "http://data4library.kr/api/keywordList"
D4L_USAGE_URL = "http://data4library.kr/api/usageAnalysisList"


def _has_empty_body(response: httpx.Response) -> bool:
    return response.text.strip() == ""


async def fetch_d4l_detail(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """정보나루 도서 상세 조회 API → 정규화 dict."""
    if not settings.D4L_API_KEY:
        return {"source": "data4library.kr", "error": "API 키 미설정 (D4L_API_KEY)"}

    params = {
        "authKey": settings.D4L_API_KEY,
        "isbn13": isbn,
        "loaninfoYN": "N",
        "format": "json",
    }
    try:
        resp = await client.get(D4L_DETAIL_URL, params=params, timeout=10)
        resp.raise_for_status()
        if _has_empty_body(resp):
            return {
                "source": "data4library.kr",
                "found": False,
                "error": "empty response from upstream",
            }
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        return {"source": "data4library.kr", "error": f"HTTP {exc.response.status_code}"}
    except Exception as exc:  # pragma: no cover - network failure path
        return {"source": "data4library.kr", "error": str(exc)}

    detail = data.get("response", {}).get("detail", [])
    if not detail:
        return {"source": "data4library.kr", "found": False}

    first = detail[0] if isinstance(detail, list) else detail
    book = first.get("book") if isinstance(first, dict) else None
    if not book:
        return {"source": "data4library.kr", "found": False}

    return {
        "source": "data4library.kr",
        "found": True,
        "title": book.get("bookname", ""),
        "author": book.get("authors", ""),
        "publisher": book.get("publisher", ""),
        "publish_year": book.get("publication_year", ""),
        "isbn": book.get("isbn", ""),
        "isbn13": book.get("isbn13", ""),
        "isbn_add_code": book.get("addition_symbol", ""),
        "volume": book.get("vol", ""),
        "class_no": book.get("class_no", ""),
        "class_nm": book.get("class_nm", ""),
        "description": book.get("description", ""),
        "cover_url": book.get("bookImageURL", ""),
    }


async def fetch_d4l_keywords(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """정보나루 키워드 목록 API → [{word, weight}] (가중치 내림차순)."""
    if not settings.D4L_API_KEY:
        return {"source": "keywordList", "found": False, "keywords": []}

    params = {
        "authKey": settings.D4L_API_KEY,
        "isbn13": isbn,
        "additionalYN": "N",
        "format": "json",
    }
    try:
        resp = await client.get(D4L_KEYWORD_URL, params=params, timeout=10)
        resp.raise_for_status()
        if _has_empty_body(resp):
            return {
                "source": "keywordList",
                "found": False,
                "keywords": [],
                "error": "empty response from upstream",
            }
        data = resp.json()
    except Exception as exc:  # pragma: no cover - network failure path
        return {"source": "keywordList", "found": False, "keywords": [], "error": str(exc)}

    items = data.get("response", {}).get("items", [])
    keywords: list[dict[str, Any]] = []
    for item in items:
        keyword = item.get("item", item)
        word = keyword.get("word", "")
        weight = keyword.get("weight", "")
        if word:
            try:
                numeric_weight = float(weight)
            except (ValueError, TypeError):
                numeric_weight = 0.0
            keywords.append({"word": word, "weight": numeric_weight})

    keywords.sort(key=lambda value: value["weight"], reverse=True)
    return {"source": "keywordList", "found": bool(keywords), "keywords": keywords}


async def fetch_d4l_usage(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """정보나루 이용 분석 API → 함께 대출된 도서만 취함."""
    if not settings.D4L_API_KEY:
        return {"source": "usageAnalysisList", "found": False, "co_loan_books": []}

    params = {
        "authKey": settings.D4L_API_KEY,
        "isbn13": isbn,
        "format": "json",
    }
    try:
        resp = await client.get(D4L_USAGE_URL, params=params, timeout=10)
        resp.raise_for_status()
        if _has_empty_body(resp):
            return {
                "source": "usageAnalysisList",
                "found": False,
                "co_loan_books": [],
                "error": "empty response from upstream",
            }
        data = resp.json()
    except Exception as exc:  # pragma: no cover - network failure path
        return {"source": "usageAnalysisList", "found": False, "co_loan_books": [], "error": str(exc)}

    raw_books = data.get("response", {}).get("coLoanBooks", [])
    co_loan_books: list[dict[str, str]] = []
    for entry in raw_books:
        book = entry.get("book", entry)
        name = book.get("bookname", "")
        if name:
            co_loan_books.append(
                {
                    "bookname": name,
                    "isbn13": book.get("isbn13", ""),
                    "authors": book.get("authors", ""),
                }
            )

    return {
        "source": "usageAnalysisList",
        "found": bool(co_loan_books),
        "co_loan_books": co_loan_books,
    }
