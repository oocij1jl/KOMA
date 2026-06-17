"""
 /api/generate  ─  LLM 프롬프트 조립 라우터

 현재 단계에서는 LLM 호출 없이,
 lookup 결과를 바탕으로 LLM 프롬프트 문자열만 반환한다.
"""

import importlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.llm import LLMInputPayload as LLMInputPayloadType
    from backend.schemas.lookup import LookupResponseSchema as LookupResponseSchemaType

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas.lookup import LookupResponseSchema
    from backend.services.llm_input_builder import build_llm_input
    from backend.services.marc_generator import build_prompt
    from backend.services.lookup_service import lookup_one
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    LookupResponseSchema = cast(
        type["LookupResponseSchemaType"],
        importlib.import_module("schemas.lookup").LookupResponseSchema,
    )
    build_llm_input = cast(
        Callable[["LookupResponseSchemaType"], "LLMInputPayloadType"],
        importlib.import_module("services.llm_input_builder").build_llm_input,
    )
    build_prompt = cast(
        Callable[["LLMInputPayloadType"], str],
        importlib.import_module("services.marc_generator").build_prompt,
    )
    lookup_one = cast(
        Callable[[httpx.AsyncClient, str], Awaitable[dict[str, object]]],
        importlib.import_module("services.lookup_service").lookup_one,
    )


router = APIRouter()


class GeneratePayloadRequest(BaseModel):
    isbn: str


@router.post("/generate", response_class=PlainTextResponse)
@router.post("/generate/marc", response_class=PlainTextResponse)
async def generate_marc(body: GeneratePayloadRequest) -> str:
    """ISBN 조회 후 LLM 프롬프트 문자열을 조립해 반환한다."""
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
    llm_input = build_llm_input(lookup_model)
    # TODO: 여기에 LLM 호출 예정
    return build_prompt(llm_input)
