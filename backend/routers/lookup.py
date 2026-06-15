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

import httpx
from fastapi import APIRouter, HTTPException, Query

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas.lookup import BulkIsbnRequest
    from backend.services.lookup_service import lookup_one
    from backend.utils.isbn import normalize_isbn
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from schemas.lookup import BulkIsbnRequest
    from services.lookup_service import lookup_one
    from utils.isbn import normalize_isbn


router = APIRouter()


@router.get("/lookup/isbn")
async def lookup_isbn(
    isbn: str = Query(..., description="조회할 ISBN (10/13자리, 하이픈 허용)"),
):
    """ISBN으로 국중도 + 정보나루(상세·키워드·이용분석)를 병합 조회."""
    try:
        clean = normalize_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with httpx.AsyncClient() as client:
        result = await lookup_one(client, clean)

    if not result["found"]:
        raise HTTPException(
            status_code=404,
            detail=f"ISBN {clean} 에 해당하는 서지정보를 찾을 수 없습니다.",
        )

    result.pop("found", None)
    return result


@router.post("/lookup/isbn/bulk")
async def lookup_isbn_bulk(body: BulkIsbnRequest):
    """여러 ISBN을 한 번에 조회 (각 ISBN별 4개 API 병합)."""
    normalized: list[str] = []
    errors: list[dict[str, str]] = []

    for raw in body.isbns:
        try:
            normalized.append(normalize_isbn(raw))
        except ValueError as exc:
            errors.append({"isbn": raw, "error": str(exc)})

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "유효하지 않은 ISBN이 포함되어 있습니다.", "errors": errors},
        )

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(lookup_one(client, isbn) for isbn in normalized))

    return {"total": len(results), "results": list(results)}
