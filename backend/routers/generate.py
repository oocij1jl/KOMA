"""
 /api/generate  ─  LLM 기반 MARC 생성 라우터
"""

import importlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.llm import LLMInputPayload as LLMInputPayloadType
    from backend.schemas.llm_output import GenerateResult as GenerateResultType
    from backend.schemas.lookup import LookupResponseSchema as LookupResponseSchemaType

try:  # pragma: no cover - import path depends on startup context
    from backend.clients.llm_client import LLMClientError
    from backend.schemas.llm_output import GenerateResult
    from backend.schemas.lookup import LookupResponseSchema
    from backend.services.llm_input_builder import build_llm_input
    from backend.services.marc_generator import generate_marc as generate_marc_result
    from backend.services.lookup_service import lookup_one
    from backend.services.output_validator import OutputValidationError
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    LLMClientError = importlib.import_module("clients.llm_client").LLMClientError
    OutputValidationError = importlib.import_module("services.output_validator").OutputValidationError
    GenerateResult = cast(
        type["GenerateResultType"],
        importlib.import_module("schemas.llm_output").GenerateResult,
    )
    LookupResponseSchema = cast(
        type["LookupResponseSchemaType"],
        importlib.import_module("schemas.lookup").LookupResponseSchema,
    )
    build_llm_input = cast(
        Callable[["LookupResponseSchemaType"], "LLMInputPayloadType"],
        importlib.import_module("services.llm_input_builder").build_llm_input,
    )
    generate_marc_result = cast(
        Callable[["LLMInputPayloadType"], Awaitable["GenerateResultType"]],
        importlib.import_module("services.marc_generator").generate_marc,
    )
    lookup_one = cast(
        Callable[[httpx.AsyncClient, str], Awaitable[dict[str, object]]],
        importlib.import_module("services.lookup_service").lookup_one,
    )


router = APIRouter()


class GeneratePayloadRequest(BaseModel):
    isbn: str


@router.post("/generate", response_model=GenerateResult)
@router.post("/generate/marc", response_model=GenerateResult)
async def generate_marc(body: GeneratePayloadRequest) -> "GenerateResultType":
    """ISBN 조회 후 LLM을 호출해 GenerateResult JSON을 반환한다."""
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
    try:
        generated = await generate_marc_result(llm_input)
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except OutputValidationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return cast("GenerateResultType", generated)
