"""
/api/lookup  ─  외부 서지 API 조회 라우터  (스키마 v2.1 대응)

연동 API (총 4개)
  [biblio 수집]
  1. 국립중앙도서관 ISBN 서지정보
     URL: https://www.nl.go.kr/seoji/SearchApi.do      인증: cert_key
  2. 도서관 정보나루 도서 상세 조회
     URL: http://data4library.kr/api/srchDtlList        인증: authKey

  [evidence 수집 — 차별점(653/056/082 추론) 연료]
  3. 도서관 정보나루 도서 키워드 목록
     URL: http://data4library.kr/api/keywordList         인증: authKey
  4. 도서관 정보나루 도서별 이용 분석 (함께 대출된 도서)
     URL: http://data4library.kr/api/usageAnalysisList   인증: authKey

응답 구조 (스키마 v2.1)
  {
    "isbn": "...",
    "biblio":   { ... },   # 가져오기 필드용 확정값
    "evidence": { ... },   # 추론 필드용 원재료 (키워드/책소개/함께대출도서/번역신호)
    "raw":      { ... }    # 원응답 (프론트 로컬 저장 후 '원문 보기'용)
  }

엔드포인트
  GET  /api/lookup/isbn?isbn={isbn}    단건 (4개 API 병합)
  POST /api/lookup/isbn/bulk           다건 (최대 10개)
"""

import re
import asyncio
import httpx
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


def _strip_price(raw: str) -> str:
    """가격 정규화: 콤마·통화기호 제거 후 숫자만 → '₩' 접두. (스키마 v2.1: ₩는 값에 포함)"""
    if not raw:
        return ""
    digits = re.sub(r"[^\d]", "", raw)
    return f"₩{digits}" if digits else ""


# 번역서 1차 탐지용 신호어 (최종 판단은 LLM이 description 읽고 확정)
_TRANS_HINTS = ("옮김", "번역", "역자", "역주", "translated", "옮긴이")


def _detect_translation(author: str, description: str) -> dict:
    """번역 정황 1차 탐지. detected와 근거 hints만 제공(추정 원저자명은 생성하지 않음)."""
    hints = []
    blob = f"{author} {description}"
    for h in _TRANS_HINTS:
        if h in blob:
            hints.append(f"'{h}' 표현 발견")
    return {"detected": bool(hints), "hints": hints}


# ---------------------------------------------------------------------------
# 1. 국립중앙도서관 클라이언트  (biblio)
# ---------------------------------------------------------------------------

NL_SEOJI_URL = "https://www.nl.go.kr/seoji/SearchApi.do"


async def fetch_nl_isbn(client: httpx.AsyncClient, isbn: str) -> dict:
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
        "title":           raw.get("TITLE", ""),
        "author":          raw.get("AUTHOR", ""),
        "publisher":       raw.get("PUBLISHER", ""),
        "publish_predate": raw.get("PUBLISH_PREDATE", ""),  # 출판예정일(yyyymmdd), 발행일 아님
        "isbn":            raw.get("EA_ISBN", ""),
        "isbn_add_code":   raw.get("EA_ADD_CODE", ""),
        "set_isbn":        raw.get("SET_ISBN", ""),
        "set_add_code":    raw.get("SET_ADD_CODE", ""),
        "set_expression":  raw.get("SET_EXPRESSION", ""),
        "price":           _strip_price(raw.get("PRE_PRICE", "")),  # 020 ▼c
        "edition_stmt":    raw.get("EDITION_STMT", ""),
        "series_title":    raw.get("SERIES_TITLE", ""),
        "series_no":       raw.get("SERIES_NO", ""),
        "volume":          raw.get("VOL", ""),
        "page":            raw.get("PAGE", ""),
        "book_size":       raw.get("BOOK_SIZE", ""),
        "form":            raw.get("FORM", ""),
        "kdc":             raw.get("KDC", ""),
        "ddc":             raw.get("DDC", ""),
        "subject":         raw.get("SUBJECT", ""),
        "ebook_yn":        raw.get("EBOOK_YN", ""),
        "cip_yn":          raw.get("CIP_YN", ""),
        "control_no":      raw.get("CONTROL_NO", ""),  # MARC 생성 금지, 표시만
        "cover_url":       raw.get("TITLE_URL", ""),
        "toc_url":         raw.get("BOOK_TB_CNT_URL", ""),
        "intro_url":       raw.get("BOOK_INTRODUCTION_URL", ""),
    }


# ---------------------------------------------------------------------------
# 2. 정보나루 도서 상세 조회  (biblio 보강 + description)
# ---------------------------------------------------------------------------

D4L_DETAIL_URL = "http://data4library.kr/api/srchDtlList"


async def fetch_d4l_detail(client: httpx.AsyncClient, isbn: str) -> dict:
    """정보나루 도서 상세 조회 API → 정규화 dict.
    실제 응답 구조: { "response": { "detail": [ { "book": {...} } ] } }
    """
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

    detail = data.get("response", {}).get("detail", [])
    if not detail:
        return {"source": "data4library.kr", "found": False}
    first = detail[0] if isinstance(detail, list) else detail
    book = first.get("book", None) if isinstance(first, dict) else None
    if not book:
        return {"source": "data4library.kr", "found": False}

    return {
        "source": "data4library.kr",
        "found": True,
        "title":        book.get("bookname", ""),
        "author":       book.get("authors", ""),
        "publisher":    book.get("publisher", ""),
        "publish_year": book.get("publication_year", ""),
        "isbn":         book.get("isbn", ""),
        "isbn13":       book.get("isbn13", ""),
        "isbn_add_code": book.get("addition_symbol", ""),
        "volume":       book.get("vol", ""),
        "class_no":     book.get("class_no", ""),
        "class_nm":     book.get("class_nm", ""),
        "description":  book.get("description", ""),
        "cover_url":    book.get("bookImageURL", ""),
    }


# ---------------------------------------------------------------------------
# 3. 정보나루 도서 키워드 목록  (evidence — 653/056/082 주 연료)
# ---------------------------------------------------------------------------

D4L_KEYWORD_URL = "http://data4library.kr/api/keywordList"


async def fetch_d4l_keywords(client: httpx.AsyncClient, isbn: str) -> dict:
    """정보나루 키워드 목록 API → [{word, weight}] (가중치 내림차순).
    실제 응답 구조: { "response": { "items": [ { "item": {"word":..., "weight":...} } ] } }
    """
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
        data = resp.json()
    except Exception as e:
        return {"source": "keywordList", "found": False, "keywords": [], "error": str(e)}

    items = data.get("response", {}).get("items", [])
    keywords = []
    for it in items:
        kw = it.get("item", it)  # { "item": {...} } 중첩 구조 처리
        word = kw.get("word", "")
        weight = kw.get("weight", "")
        if word:
            try:
                w = float(weight)
            except (ValueError, TypeError):
                w = 0.0
            keywords.append({"word": word, "weight": w})

    keywords.sort(key=lambda x: x["weight"], reverse=True)
    return {"source": "keywordList", "found": bool(keywords), "keywords": keywords}


# ---------------------------------------------------------------------------
# 4. 정보나루 도서별 이용 분석  (evidence — 함께 대출된 도서)
# ---------------------------------------------------------------------------

D4L_USAGE_URL = "http://data4library.kr/api/usageAnalysisList"


async def fetch_d4l_usage(client: httpx.AsyncClient, isbn: str) -> dict:
    """정보나루 이용 분석 API → 함께 대출된 도서(coLoanBooks)만 취함.
    실제 응답 구조: { "response": { "coLoanBooks": [ { "book": {...} } ] } }
    키워드·description은 srchDtlList와 중복이라 무시.
    """
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
        data = resp.json()
    except Exception as e:
        return {"source": "usageAnalysisList", "found": False, "co_loan_books": [], "error": str(e)}

    co_raw = data.get("response", {}).get("coLoanBooks", [])
    co_books = []
    for entry in co_raw:
        b = entry.get("book", entry)
        name = b.get("bookname", "")
        if name:
            co_books.append({
                "bookname": name,
                "isbn13":   b.get("isbn13", ""),
                "authors":  b.get("authors", ""),
            })
    return {"source": "usageAnalysisList", "found": bool(co_books), "co_loan_books": co_books}


# ---------------------------------------------------------------------------
# 병합 — biblio
# ---------------------------------------------------------------------------

def _pick(*values: str) -> str:
    """비어 있지 않은 첫 번째 값."""
    for v in values:
        if v:
            return v
    return ""


def merge_biblio(nl: dict, d4l: dict) -> dict:
    """국중도 + 정보나루 상세 → biblio (스키마 v2.1)."""
    nl_found = nl.get("found", False)
    d4l_found = d4l.get("found", False)

    field_sources: dict = {}

    def pick_src(key, *pairs):
        """(value, source) 쌍에서 첫 비어있지 않은 값 + 출처 기록."""
        for val, src in pairs:
            if val:
                field_sources[key] = src
                return val
        return ""

    return {
        "found": nl_found or d4l_found,

        # 020
        "isbn_ea":        pick_src("isbn_ea", (nl.get("isbn"), "nl"), (d4l.get("isbn13"), "d4l"), (d4l.get("isbn"), "d4l")),
        "isbn_add_code":  pick_src("isbn_add_code", (nl.get("isbn_add_code"), "nl"), (d4l.get("isbn_add_code"), "d4l")),
        "set_isbn":       _pick(nl.get("set_isbn", "")),
        "set_add_code":   _pick(nl.get("set_add_code", "")),
        "set_expression": _pick(nl.get("set_expression", "")),
        "price":          pick_src("price", (nl.get("price"), "nl")),  # 정보나루 가격 미제공

        # 245
        "title":  pick_src("title", (nl.get("title"), "nl"), (d4l.get("title"), "d4l")),
        "author": pick_src("author", (nl.get("author"), "nl"), (d4l.get("author"), "d4l")),
        "volume": pick_src("volume", (nl.get("volume"), "nl"), (d4l.get("volume"), "d4l")),

        # 260  — publish_year는 정보나루(실제 발행년) 우선, 국중도 PUBLISH_PREDATE는 예정일이라 후순위
        "pub_place":       "",  # 두 API 모두 미제공 → 검수 필요
        "publisher":       pick_src("publisher", (nl.get("publisher"), "nl"), (d4l.get("publisher"), "d4l")),
        "publish_year":    pick_src("publish_year", (d4l.get("publish_year"), "d4l"), (nl.get("publish_predate", "")[:4], "nl")),
        "publish_predate": _pick(nl.get("publish_predate", "")),

        # 분류 (검수 필수)
        "kdc":         pick_src("kdc", (nl.get("kdc"), "nl"), (d4l.get("class_no"), "d4l")),
        "kdc_edition": "",  # 판차 미제공 → 검수
        "kdc_name":    _pick(d4l.get("class_nm", "")),
        "ddc":         pick_src("ddc", (nl.get("ddc"), "nl")),
        "ddc_edition": "",
        "subject":     pick_src("subject", (nl.get("subject"), "nl")),

        # 조건부
        "edition_stmt": _pick(nl.get("edition_stmt", "")),
        "series_title": _pick(nl.get("series_title", "")),
        "series_no":    _pick(nl.get("series_no", "")),
        "page":         _pick(nl.get("page", "")),
        "book_size":    _pick(nl.get("book_size", "")),
        "form":         _pick(nl.get("form", "")),
        "ebook_yn":     _pick(nl.get("ebook_yn", "")),
        "description":  pick_src("description", (d4l.get("description"), "d4l")),

        # 임의생성 금지·표시 전용
        "control_no": _pick(nl.get("control_no", "")),

        # UI 표시 전용
        "cover_url": pick_src("cover_url", (nl.get("cover_url"), "nl"), (d4l.get("cover_url"), "d4l")),
        "toc_url":   _pick(nl.get("toc_url", "")),
        "intro_url": _pick(nl.get("intro_url", "")),

        "field_sources": field_sources,
    }


# ---------------------------------------------------------------------------
# 병합 — evidence
# ---------------------------------------------------------------------------

def merge_evidence(biblio: dict, kw: dict, usage: dict) -> dict:
    """키워드 + 이용분석 + biblio 일부 → evidence (스키마 v2.1)."""
    keywords    = kw.get("keywords", [])
    co_loan     = usage.get("co_loan_books", [])
    description = biblio.get("description", "")
    author      = biblio.get("author", "")

    trans = _detect_translation(author, description)

    return {
        "keywords":    keywords,
        "description": description,
        "co_loan_books": co_loan,
        "title":       biblio.get("title", ""),
        "author":      author,
        "kdc_from_api": biblio.get("kdc", ""),
        "ddc_from_api": biblio.get("ddc", ""),
        "translation_signals": trans,
        "available": {
            "keywords":     bool(keywords),
            "description":  bool(description),
            "co_loan_books": bool(co_loan),
        },
    }


# ---------------------------------------------------------------------------
# 단건 조회 코어
# ---------------------------------------------------------------------------

async def lookup_one(client: httpx.AsyncClient, isbn: str) -> dict:
    """4개 API 병렬 호출 → biblio/evidence/raw 분리 반환."""
    nl, d4l, kw, usage = await asyncio.gather(
        fetch_nl_isbn(client, isbn),
        fetch_d4l_detail(client, isbn),
        fetch_d4l_keywords(client, isbn),
        fetch_d4l_usage(client, isbn),
    )

    biblio   = merge_biblio(nl, d4l)
    evidence = merge_evidence(biblio, kw, usage)

    return {
        "isbn":    isbn,
        "biblio":  biblio,
        "evidence": evidence,
        "raw": {  # 프론트가 로컬 저장 후 '원문 보기'에 사용
            "nl":          nl,
            "d4l_detail":  d4l,
            "d4l_keyword": kw,
            "d4l_usage":   usage,
        },
        "found": biblio["found"],
    }


# ---------------------------------------------------------------------------
# 엔드포인트 - 단건
# ---------------------------------------------------------------------------

@router.get("/lookup/isbn")
async def lookup_isbn(
    isbn: str = Query(..., description="조회할 ISBN (10/13자리, 하이픈 허용)"),
):
    """ISBN으로 국중도 + 정보나루(상세·키워드·이용분석)를 병합 조회."""
    try:
        clean = normalize_isbn(isbn)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    async with httpx.AsyncClient() as client:
        result = await lookup_one(client, clean)

    if not result["found"]:
        raise HTTPException(
            status_code=404,
            detail=f"ISBN {clean} 에 해당하는 서지정보를 찾을 수 없습니다.",
        )

    result.pop("found", None)
    return result


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
    """여러 ISBN을 한 번에 조회 (각 ISBN별 4개 API 병합)."""
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

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(lookup_one(client, isbn) for isbn in normalized))

    return {
        "total": len(results),
        "results": list(results),
    }
