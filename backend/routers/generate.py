"""
/api/generate  ─  LLM 입력 payload 조립 라우터

현재 단계에서는 LLM 호출 없이,
lookup 결과를 바탕으로 LLMInputPayload만 반환한다.
"""

import importlib

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas.llm import LLMInputPayload
    from backend.schemas.lookup import LookupResponseSchema
    from backend.services.llm_input_builder import build_llm_input
    from backend.services.lookup_service import lookup_one
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    LLMInputPayload = importlib.import_module("schemas.llm").LLMInputPayload
    LookupResponseSchema = importlib.import_module("schemas.lookup").LookupResponseSchema
    build_llm_input = importlib.import_module("services.llm_input_builder").build_llm_input
    lookup_one = importlib.import_module("services.lookup_service").lookup_one


router = APIRouter()


class GeneratePayloadRequest(BaseModel):
    isbn: str


@router.post("/generate", response_model=LLMInputPayload)
@router.post("/generate/marc", response_model=LLMInputPayload)
async def generate_marc(body: GeneratePayloadRequest):
    """ISBN 조회 후 LLM 입력 payload를 조립해 반환한다."""
    try:
        async with httpx.AsyncClient() as client:
            lookup_result = await lookup_one(client, body.isbn)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not lookup_result["found"]:
        raise HTTPException(
            status_code=404,
            detail=f"ISBN {lookup_result['isbn']} 에 해당하는 서지정보를 찾을 수 없습니다.",
        )

    lookup_model = LookupResponseSchema.model_validate(lookup_result)
    return build_llm_input(lookup_model)
