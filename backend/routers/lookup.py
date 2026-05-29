"""
/api/lookup  ─  외부 서지 API 조회 라우터

연동 API
  1. 국립중앙도서관 ISBN 서지정보
     URL: https://www.nl.go.kr/seoji/SearchApi.do
     인증: cert_key (쿼리 파라미터)

  2. 도서관 정보나루 도서 상세 조회
     URL: http://data4library.kr/api/srchDtlList
     인증: authKey (쿼리 파라미터)

엔드포인트
  GET /api/lookup/isbn?isbn={isbn}           단건 조회 (두 API 병합)
  POST /api/lookup/isbn/bulk                  다건 조회 (최대 10개)
"""

import re
import asyncio
import httpx
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from config import settings

router = APIRouter()

# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

ISBN10_RE = re.compile(r"^\d{9}[\dX]$")
ISBN13_RE = re.compile(r"^\d{13}$")


def normalize_isbn(raw: str) -> str:
    """하이픈 제거 후 형식 검증. 잘못된 ISBN은 ValueError."""
    isbn = raw.replace("-", "").strip()
    if not (ISBN10_RE.match(isbn) or ISBN13_RE.match(isbn)):
        raise ValueError(f"유효하지 않은 ISBN 형식: {raw!r}")
    return isbn


# ---------------------------------------------------------------------------
# 국립중앙도서관 클라이언트
# ---------------------------------------------------------------------------

NL_SEOJI_URL = "https://www.nl.go.kr/seoji/SearchApi.do"

async def fetch_nl_isbn(client: httpx.AsyncClient, isbn: str) -> dict:
    """국립중앙도서관 ISBN 서지정보 API 호출 → 정규화된 dict 반환."""
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
    except httpx.HTTPStatusError as e:
        return {"source": "nl.go.kr", "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"source": "nl.go.kr", "error": str(e)}

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
        "publish_date": raw.get("PUBLISH_PREDATE", ""),   # 출판예정일(yyyymmdd)
        "isbn": raw.get("EA_ISBN", ""),
        "isbn_add_code": raw.get("EA_ADD_CODE", ""),
        "set_isbn": raw.get("SET_ISBN", ""),
        "edition": raw.get("EDITION_STMT", ""),
        "series_title": raw.get("SERIES_TITLE", ""),
        "series_no": raw.get("SERIES_NO", ""),
        "volume": raw.get("VOL", ""),
        "page": raw.get("PAGE", ""),          # 페이지 수 (있을 때만)
        "book_size": raw.get("BOOK_SIZE", ""),  # 크기 (있을 때만)
        "form": raw.get("FORM", ""),
        "kdc": raw.get("KDC", ""),            # AI 검수 필수 필드
        "ddc": raw.get("DDC", ""),            # AI 검수 필수 필드
        "subject": raw.get("SUBJECT", ""),
        "ebook_yn": raw.get("EBOOK_YN", ""),
        "cip_yn": raw.get("CIP_YN", ""),
        "control_no": raw.get("CONTROL_NO", ""),
        "cover_url": raw.get("TITLE_URL", ""),
        "toc_url": raw.get("BOOK_TB_CNT_URL", ""),
        "intro_url": raw.get("BOOK_INTRODUCTION_URL", ""),
    }


# ---------------------------------------------------------------------------
# 도서관 정보나루 클라이언트
# ---------------------------------------------------------------------------

D4L_DETAIL_URL = "http://data4library.kr/api/srchDtlList"

async def fetch_d4l_isbn(client: httpx.AsyncClient, isbn: str) -> dict:
    """도서관 정보나루 도서 상세 조회 API 호출 → 정규화된 dict 반환."""
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
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return {"source": "data4library.kr", "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"source": "data4library.kr", "error": str(e)}

    # 응답 구조: { "detail": { "book": { ... } } }
    book = data.get("detail", {}).get("book", None)

    # 정보나루는 단건 결과가 dict 또는 리스트일 수 있음
    if isinstance(book, list):
        book = book[0] if book else None

    if not book:
        return {"source": "data4library.kr", "found": False}

    return {
        "source": "data4library.kr",
        "found": True,
        "title": book.get("bookname", ""),
        "author": book.get("authors", ""),
        "publisher": book.get("publisher", ""),
        "publish_date": book.get("publication_date", ""),
        "publish_year": book.get("publication_year", ""),
        "isbn": book.get("isbn", ""),
        "isbn13": book.get("isbn13", ""),
        "isbn_add_code": book.get("addition_symbol", ""),
        "volume": book.get("vol", ""),
        "class_no": book.get("class_no", ""),    # KDC 주제분류
        "class_nm": book.get("class_nm", ""),
        "description": book.get("description", ""),
        "cover_url": book.get("bookImageURL", ""),
    }


# ---------------------------------------------------------------------------
# 병합 로직
# ---------------------------------------------------------------------------

def merge_biblio(nl: dict, d4l: dict) -> dict:
    """두 API 결과를 병합. 필드별로 더 상세한 값 우선 사용."""

    def pick(*values: str) -> str:
        """비어 있지 않은 첫 번째 값 반환."""
        for v in values:
            if v:
                return v
        return ""

    nl_found = nl.get("found", False)
    d4l_found = d4l.get("found", False)

    merged = {
        "found": nl_found or d4l_found,
        "sources": {
            "nl": nl,
            "d4l": d4l,
        },
        # --- 필수 필드 (020, 245, 260, 700/710 생성 기반) ---
        "title":        pick(nl.get("title"), d4l.get("title")),
        "author":       pick(nl.get("author"), d4l.get("author")),
        "publisher":    pick(nl.get("publisher"), d4l.get("publisher")),
        "publish_year": pick(
            nl.get("publish_date", "")[:4],   # yyyymmdd → yyyy
            d4l.get("publish_year"),
            d4l.get("publish_date", "")[:4],
        ),
        "isbn":         pick(nl.get("isbn"), d4l.get("isbn13"), d4l.get("isbn")),
        "isbn_add_code": pick(nl.get("isbn_add_code"), d4l.get("isbn_add_code")),
        "set_isbn":     pick(nl.get("set_isbn"), ""),
        # --- 조건부 필드 ---
        "edition":      pick(nl.get("edition"), ""),
        "series_title": pick(nl.get("series_title"), ""),
        "series_no":    pick(nl.get("series_no"), ""),
        "volume":       pick(nl.get("volume"), d4l.get("volume")),
        # --- 페이지/크기: 명확한 값만 (없으면 빈 문자열) ---
        "page":         pick(nl.get("page"), ""),
        "book_size":    pick(nl.get("book_size"), ""),
        # --- 분류 (AI 검수 필수) ---
        "kdc":          pick(nl.get("kdc"), d4l.get("class_no")),
        "kdc_name":     pick(d4l.get("class_nm"), ""),
        "ddc":          pick(nl.get("ddc"), ""),
        "subject":      pick(nl.get("subject"), ""),
        # --- 기타 ---
        "description":  pick(d4l.get("description"), ""),
        "cover_url":    pick(nl.get("cover_url"), d4l.get("cover_url")),
        "toc_url":      pick(nl.get("toc_url"), ""),
        "ebook_yn":     pick(nl.get("ebook_yn"), ""),
        "form":         pick(nl.get("form"), ""),
        "control_no":   pick(nl.get("control_no"), ""),
    }
    return merged


# ---------------------------------------------------------------------------
# 엔드포인트 - 단건
# ---------------------------------------------------------------------------

@router.get("/lookup/isbn")
async def lookup_isbn(
    isbn: str = Query(..., description="조회할 ISBN (10자리 또는 13자리, 하이픈 허용)"),
):
    """
    ISBN으로 국립중앙도서관 + 도서관 정보나루 서지정보를 동시에 조회하여 병합 반환.
    """
    try:
        clean_isbn = normalize_isbn(isbn)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    async with httpx.AsyncClient() as client:
        nl_result, d4l_result = await asyncio.gather(
            fetch_nl_isbn(client, clean_isbn),
            fetch_d4l_isbn(client, clean_isbn),
        )

    merged = merge_biblio(nl_result, d4l_result)

    if not merged["found"]:
        raise HTTPException(
            status_code=404,
            detail=f"ISBN {clean_isbn} 에 해당하는 서지정보를 찾을 수 없습니다.",
        )

    return {
        "isbn": clean_isbn,
        "biblio": merged,
    }


# ---------------------------------------------------------------------------
# 엔드포인트 - 다건
# ---------------------------------------------------------------------------

class BulkIsbnRequest(BaseModel):
    isbns: list[str]

    @field_validator("isbns")
    @classmethod
    def check_limit(cls, v):
        if len(v) == 0:
            raise ValueError("ISBN 목록이 비어 있습니다.")
        if len(v) > 10:
            raise ValueError("한 번에 최대 10개까지 조회할 수 있습니다.")
        return v


@router.post("/lookup/isbn/bulk")
async def lookup_isbn_bulk(body: BulkIsbnRequest):
    """
    여러 ISBN을 한 번에 조회. 각 ISBN별로 국립중앙도서관 + 정보나루 병합 결과 반환.
    """
    # 모든 ISBN 정규화 (오류 있으면 422)
    normalized: list[str] = []
    errors: list[dict] = []

    for raw in body.isbns:
        try:
            normalized.append(normalize_isbn(raw))
        except ValueError as e:
            errors.append({"isbn": raw, "error": str(e)})

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "유효하지 않은 ISBN이 포함되어 있습니다.", "errors": errors},
        )

    async def fetch_one(client: httpx.AsyncClient, isbn: str) -> dict:
        nl, d4l = await asyncio.gather(
            fetch_nl_isbn(client, isbn),
            fetch_d4l_isbn(client, isbn),
        )
        merged = merge_biblio(nl, d4l)
        return {"isbn": isbn, "biblio": merged, "found": merged["found"]}

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(fetch_one(client, isbn) for isbn in normalized))

    return {
        "total": len(results),
        "results": list(results),
    }