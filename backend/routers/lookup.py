from __future__ import annotations

"""
/api/lookup  ─  외부 서지 API 조회 라우터  (스키마 v2.1 대응)

응답 구조
  {
    "isbn": "...",
    "biblio":   { ... },
    "evidence": { ... },
    "raw":      { ... }
  }

엔드포인트
  GET  /api/lookup/isbn?isbn={isbn}    단건 (4개 API 병합)
  POST /api/lookup/isbn/bulk           다건 (최대 10개)
"""

import asyncio
import importlib

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas.lookup import LookupResponseSchema
    from backend.services.lookup_service import lookup_one
    from backend.utils.isbn import normalize_isbn, to_isbn13
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    lookup_schemas = importlib.import_module("schemas.lookup")
    lookup_service = importlib.import_module("services.lookup_service")
    isbn_utils = importlib.import_module("utils.isbn")

    LookupResponseSchema = lookup_schemas.LookupResponseSchema
    lookup_one = lookup_service.lookup_one
    normalize_isbn = isbn_utils.normalize_isbn
    to_isbn13 = isbn_utils.to_isbn13


router = APIRouter()


class LookupBulkRequest(BaseModel):
    isbns: list[str]

    @field_validator("isbns")
    @classmethod
    def check_limit(cls, value: list[str]) -> list[str]:
        if len(value) == 0:
            raise ValueError("ISBN 목록이 비어 있습니다.")
        if len(value) > 10:
            raise ValueError("한 번에 최대 10개까지 조회할 수 있습니다.")
        return value


@router.get("/lookup/isbn")
async def lookup_isbn(
    isbn: str = Query(..., description="조회할 ISBN (10/13자리, 하이픈 허용)"),
):
    """ISBN으로 국중도 + 정보나루(상세·키워드·이용분석)를 병합 조회."""
    try:
        clean = normalize_isbn(isbn)
        to_isbn13(clean)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with httpx.AsyncClient() as client:
        result = await lookup_one(client, clean)

    if not result["found"]:
        raise HTTPException(
            status_code=404,
            detail=f"ISBN {result['isbn']} 에 해당하는 서지정보를 찾을 수 없습니다.",
        )

    return LookupResponseSchema.model_validate(result).model_dump()


@router.post("/lookup/isbn/bulk")
async def lookup_isbn_bulk(body: LookupBulkRequest):
    """여러 ISBN을 한 번에 조회 (각 ISBN별 4개 API 병합)."""
    normalized: list[str] = []
    errors: list[dict[str, str]] = []

    for raw in body.isbns:
        try:
            clean = normalize_isbn(raw)
            to_isbn13(clean)
            normalized.append(clean)
        except ValueError as exc:
            errors.append({"isbn": raw, "error": str(exc)})

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "유효하지 않은 ISBN이 포함되어 있습니다.", "errors": errors},
        )

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(lookup_one(client, isbn) for isbn in normalized))

    serialized_results = [LookupResponseSchema.model_validate(item).model_dump() for item in results]
    return {"total": len(serialized_results), "results": serialized_results}
