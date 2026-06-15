import asyncio
from typing import Any

import httpx

try:  # pragma: no cover - import path depends on startup context
    from backend.clients.data4library_client import (
        fetch_d4l_detail,
        fetch_d4l_keywords,
        fetch_d4l_usage,
    )
    from backend.clients.nl_client import fetch_nl_isbn
    from backend.services.evidence_service import merge_evidence
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from clients.data4library_client import (
        fetch_d4l_detail,
        fetch_d4l_keywords,
        fetch_d4l_usage,
    )
    from clients.nl_client import fetch_nl_isbn
    from services.evidence_service import merge_evidence


def _pick(*values: str) -> str:
    """비어 있지 않은 첫 번째 값."""
    for value in values:
        if value:
            return value
    return ""


def merge_biblio(nl: dict[str, Any], d4l: dict[str, Any]) -> dict[str, Any]:
    """국중도 + 정보나루 상세 → biblio (스키마 v2.1)."""
    nl_found = bool(nl.get("found", False))
    d4l_found = bool(d4l.get("found", False))

    field_sources: dict[str, str] = {}

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
            (nl.get("publish_predate", "")[:4], "nl"),
        ),
        "publish_predate": _pick(nl.get("publish_predate", "")),
        "kdc": pick_src("kdc", (nl.get("kdc", ""), "nl"), (d4l.get("class_no", ""), "d4l")),
        "kdc_edition": "",
        "kdc_name": _pick(d4l.get("class_nm", "")),
        "ddc": pick_src("ddc", (nl.get("ddc", ""), "nl")),
        "ddc_edition": "",
        "subject": pick_src("subject", (nl.get("subject", ""), "nl")),
        "edition_stmt": _pick(nl.get("edition_stmt", "")),
        "series_title": _pick(nl.get("series_title", "")),
        "series_no": _pick(nl.get("series_no", "")),
        "page": _pick(nl.get("page", "")),
        "book_size": _pick(nl.get("book_size", "")),
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
    """4개 API 병렬 호출 → biblio/evidence/raw 분리 반환."""
    nl, d4l, keywords_result, usage_result = await asyncio.gather(
        fetch_nl_isbn(client, isbn),
        fetch_d4l_detail(client, isbn),
        fetch_d4l_keywords(client, isbn),
        fetch_d4l_usage(client, isbn),
    )

    biblio = merge_biblio(nl, d4l)
    evidence = merge_evidence(biblio, keywords_result, usage_result)

    return {
        "isbn": isbn,
        "biblio": biblio,
        "evidence": evidence,
        "raw": {
            "nl": nl,
            "d4l_detail": d4l,
            "d4l_keyword": keywords_result,
            "d4l_usage": usage_result,
        },
        "found": biblio["found"],
    }
