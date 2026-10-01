import asyncio
import importlib
import re
from typing import Any

import httpx

try:  # pragma: no cover - import path depends on startup context
    from backend.clients.data4library_client import (
        fetch_d4l_detail,
        fetch_d4l_keywords,
        fetch_d4l_usage,
    )
    from backend.clients.aladin_client import fetch_aladin_item
    from backend.clients.kyobo_client import fetch_kyobo_detail
    from backend.clients.nl_client import fetch_nl_isbn, fetch_nl_seoji_title_statement
    from backend.config import settings
    from backend.services.evidence_service import merge_evidence
    from backend.utils.isbn import to_isbn13
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    data4library_client = importlib.import_module("clients.data4library_client")
    nl_client = importlib.import_module("clients.nl_client")
    evidence_service = importlib.import_module("services.evidence_service")
    isbn_utils = importlib.import_module("utils.isbn")

    fetch_d4l_detail = data4library_client.fetch_d4l_detail
    fetch_d4l_keywords = data4library_client.fetch_d4l_keywords
    fetch_d4l_usage = data4library_client.fetch_d4l_usage
    fetch_nl_isbn = nl_client.fetch_nl_isbn
    fetch_nl_seoji_title_statement = nl_client.fetch_nl_seoji_title_statement
    aladin_client = importlib.import_module("clients.aladin_client")
    kyobo_client = importlib.import_module("clients.kyobo_client")
    fetch_aladin_item = aladin_client.fetch_aladin_item
    fetch_kyobo_detail = kyobo_client.fetch_kyobo_detail
    settings = importlib.import_module("config").settings
    merge_evidence = evidence_service.merge_evidence
    to_isbn13 = isbn_utils.to_isbn13


SKIPPED_USAGE_RESULT: dict[str, Any] = {
    "source": "usageAnalysisList",
    "found": False,
    "co_loan_books": [],
    "error": "skipped (D4L_SKIP_USAGE)",
}


def _pick(*values: str) -> str:
    """비어 있지 않은 첫 번째 값."""
    for value in values:
        if value:
            return value
    return ""


# 상세 페이지가 본표제와 부제를 잇는 데 쓰는 구분자.
# ` = `는 245 규칙에서 대등표제($x)이므로 부제 구분자로 쓰지 않는다.
_TITLE_STATEMENT_SEPARATORS = (" - ", " : ")


def extract_subtitle(title: str, title_statement: str) -> str:
    """API 본표제를 기준으로 상세 페이지 표제사항에서 부제만 떼어낸다.

    표제사항이 API 본표제로 시작하고 그 뒤에 구분자가 있을 때만 나눈다.
    두 값이 같거나 본표제로 시작하지 않으면 부제가 없다고 본다. 화면 문자열을
    근거 없이 재단하지 않기 위한 조건이다.

    떼어낸 뒤에 다시 `:`나 `=`가 나오면 그 뒤는 책임표시나 대등표제이므로
    버린다. 245 $b에 ISBD 구두점이나 책임표시를 넣지 않기 위한 처리다.
    """

    main_title = " ".join(title.split())
    statement = " ".join(title_statement.split())
    if not main_title or not statement or not statement.startswith(main_title):
        return ""

    remainder = statement[len(main_title) :]
    for separator in _TITLE_STATEMENT_SEPARATORS:
        if remainder.startswith(separator):
            subtitle = remainder[len(separator) :]
            return re.split(r"[:=]", subtitle)[0].strip()
    return ""


def _aladin_extent(aladin: dict[str, Any] | None) -> str:
    """알라딘 `itemPage`(숫자)를 300 규칙이 읽는 `NNN p.`로 바꾼다."""

    page = str((aladin or {}).get("item_page", "")).strip()
    return f"{page} p." if page.isdigit() and int(page) > 0 else ""


def _aladin_dimensions(aladin: dict[str, Any] | None) -> str:
    """알라딘 판형(mm)을 300 규칙이 읽는 `가로*세로mm`로 바꾼다.

    세로 값이 없으면 크기를 만들지 않는다. 300은 세로 치수를 쓰기 때문이다.
    """

    source = aladin or {}
    width = str(source.get("size_width_mm", "")).strip()
    height = str(source.get("size_height_mm", "")).strip()
    if not height.isdigit() or int(height) <= 0:
        return ""
    if width.isdigit() and int(width) > 0:
        return f"{width}*{height}mm"
    return f"{height}mm"



def merge_biblio(
    nl: dict[str, Any],
    d4l: dict[str, Any],
    seoji_detail: dict[str, Any] | None = None,
    aladin: dict[str, Any] | None = None,
    kyobo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """국중도 + 정보나루 상세 → biblio (스키마 v2.1)."""
    nl_found = bool(nl.get("found", False))
    d4l_found = bool(d4l.get("found", False))

    field_sources: dict[str, str] = {}
    publish_predate = nl.get("publish_predate", "")
    publish_predate_year = publish_predate[:4] if len(publish_predate) >= 4 else ""

    def pick_src(key: str, *pairs: tuple[str, str]) -> str:
        for value, source in pairs:
            if value:
                field_sources[key] = source
                return value
        return ""

    return {
        "found": nl_found or d4l_found,
        "isbn_ea": pick_src(
            "isbn_ea",
            (nl.get("isbn", ""), "nl"),
            (d4l.get("isbn13", ""), "d4l"),
            (d4l.get("isbn", ""), "d4l"),
        ),
        "isbn_add_code": pick_src(
            "isbn_add_code",
            (nl.get("isbn_add_code", ""), "nl"),
            (d4l.get("isbn_add_code", ""), "d4l"),
        ),
        "set_isbn": _pick(nl.get("set_isbn", "")),
        "set_add_code": _pick(nl.get("set_add_code", "")),
        "set_expression": _pick(nl.get("set_expression", "")),
        "price": pick_src("price", (nl.get("price", ""), "nl")),
        "title": pick_src("title", (nl.get("title", ""), "nl"), (d4l.get("title", ""), "d4l")),
        # 부제 수집 우선순위: 공식 API(알라딘) → 국중도 상세 페이지 → 교보 상세.
        # 뒤로 갈수록 화면 구조에 의존하므로 공식 응답을 먼저 쓴다.
        "subtitle": pick_src(
            "subtitle",
            ((aladin or {}).get("subtitle", ""), "aladin"),
            (
                extract_subtitle(
                    _pick(nl.get("title", ""), d4l.get("title", "")),
                    (seoji_detail or {}).get("title_statement", ""),
                ),
                "nl_seoji_detail",
            ),
            ((kyobo or {}).get("subtitle", ""), "kyobo"),
        ),
        "author": pick_src(
            "author",
            (nl.get("author", ""), "nl"),
            (d4l.get("author", ""), "d4l"),
        ),
        "volume": pick_src(
            "volume",
            (nl.get("volume", ""), "nl"),
            (d4l.get("volume", ""), "d4l"),
        ),
        "pub_place": "",
        "publisher": pick_src(
            "publisher",
            (nl.get("publisher", ""), "nl"),
            (d4l.get("publisher", ""), "d4l"),
        ),
        "publish_year": pick_src(
            "publish_year",
            (d4l.get("publish_year", ""), "d4l"),
            (publish_predate_year, "nl"),
        ),
        "publish_predate": _pick(publish_predate),
        "kdc": pick_src("kdc", (nl.get("kdc", ""), "nl"), (d4l.get("class_no", ""), "d4l")),
        "kdc_edition": "",
        "kdc_name": _pick(d4l.get("class_nm", "")),
        "ddc": pick_src("ddc", (nl.get("ddc", ""), "nl")),
        "ddc_edition": "",
        "subject": pick_src("subject", (nl.get("subject", ""), "nl")),
        "edition_stmt": _pick(nl.get("edition_stmt", "")),
        "series_title": _pick(nl.get("series_title", "")),
        "series_no": _pick(nl.get("series_no", "")),
        # 쪽수는 교보 상품정보가 정답(목록 규칙상 마지막 번호 쪽)에 더 가깝다.
        # 33권 대조에서 교보 23건, 국중도 12건이 정답과 일치했다. 교보가 없으면 국중도, 알라딘 순이다.
        "page": pick_src(
            "page",
            ((kyobo or {}).get("page", ""), "kyobo"),
            (nl.get("page", ""), "nl"),
            (_aladin_extent(aladin), "aladin"),
        ),
        "book_size": pick_src(
            "book_size",
            (nl.get("book_size", ""), "nl"),
            ((kyobo or {}).get("book_size", ""), "kyobo"),
            (_aladin_dimensions(aladin), "aladin"),
        ),
        "form": _pick(nl.get("form", "")),
        "ebook_yn": _pick(nl.get("ebook_yn", "")),
        "description": pick_src("description", (d4l.get("description", ""), "d4l")),
        "control_no": _pick(nl.get("control_no", "")),
        "cover_url": pick_src(
            "cover_url",
            (nl.get("cover_url", ""), "nl"),
            (d4l.get("cover_url", ""), "d4l"),
        ),
        "toc_url": _pick(nl.get("toc_url", "")),
        "intro_url": _pick(nl.get("intro_url", "")),
        "field_sources": field_sources,
    }


async def lookup_one(client: httpx.AsyncClient, isbn: str) -> dict[str, Any]:
    """국중도·정보나루·알라딘 API와 국중도 상세 페이지 병렬 호출 → biblio/evidence/raw 분리 반환.

    settings.D4L_SKIP_USAGE가 켜져 있으면 정보나루 이용분석(co_loan_books)
    호출을 건너뛴다. 정보나루는 하루 500콜 한도가 있어, 책당 호출 수를
    3콜(상세+키워드+이용분석)에서 2콜(상세+키워드)로 줄여 대량 평가 시
    하루에 처리 가능한 권수를 늘리기 위함이다. 653 필드의 공동대출 근거만
    빠지고 keywords/description 근거는 그대로 유지된다.

    부제는 공식 API(알라딘) → 국중도 상세 페이지 → 교보 상세 순으로 찾고,
    쪽수는 교보 상품정보를 먼저 쓴다. 교보는 공개 API가 없어 검색·상세 2회를
    요청한다. 어느 수집원이 실패해도 나머지 결과로 계속 진행한다.
    """
    isbn13 = to_isbn13(isbn)

    async def _usage() -> dict[str, Any]:
        if settings.D4L_SKIP_USAGE:
            return SKIPPED_USAGE_RESULT
        return await fetch_d4l_usage(client, isbn13)

    nl, d4l, keywords_result, usage_result, seoji_detail, aladin, kyobo = await asyncio.gather(
        fetch_nl_isbn(client, isbn13),
        fetch_d4l_detail(client, isbn13),
        fetch_d4l_keywords(client, isbn13),
        _usage(),
        fetch_nl_seoji_title_statement(client, isbn13),
        fetch_aladin_item(client, isbn13),
        fetch_kyobo_detail(client, isbn13),
    )

    biblio = merge_biblio(nl, d4l, seoji_detail, aladin, kyobo)
    evidence = merge_evidence(biblio, keywords_result, usage_result)

    return {
        "isbn": isbn13,
        "biblio": biblio,
        "evidence": evidence,
        "raw": {
            "nl": nl,
            "d4l_detail": d4l,
            "d4l_keyword": keywords_result,
            "d4l_usage": usage_result,
            "nl_seoji_detail": seoji_detail,
            "aladin": aladin,
            "kyobo": kyobo,
        },
        "found": biblio["found"],
    }
