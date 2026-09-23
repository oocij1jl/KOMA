"""
 /api/generate  ─  LLM 기반 MARC 생성 라우터
"""

import asyncio
import importlib
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.llm import LLMInputPayload as LLMInputPayloadType
    from backend.schemas.llm_output import GenerateResult as GenerateResultType
    from backend.schemas.lookup import LookupResponseSchema as LookupResponseSchemaType

try:  # pragma: no cover - import path depends on startup context
    from backend.clients.http_client import get_http_client
    from backend.clients.llm_client import LLMClientError
    from backend.schemas.llm_output import GenerateResult
    from backend.schemas.lookup import LookupResponseSchema
    from backend.services.llm_input_builder import build_llm_input
    from backend.services.marc_generator import generate_marc as generate_marc_result
    from backend.services.lookup_service import lookup_one
    from backend.services.output_validator import OutputValidationError
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    get_http_client = importlib.import_module("clients.http_client").get_http_client
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


logger = logging.getLogger(__name__)

router = APIRouter()

GENERATE_BULK_CONCURRENCY = 3


async def get_generate_semaphore(request: Request) -> asyncio.Semaphore:
    """lifespan이 request.state에 넣어둔 공유 세마포어를 반환한다.

    요청마다 새로 만들지 않는 이유: (1) 여러 bulk 요청이 겹쳐 들어와도 동시
    LLM 호출 총량을 하나의 상한으로 묶기 위해, (2) asyncio 동기화 객체를
    다른 이벤트 루프에서 재사용하면 RuntimeError가 나므로 http_client와
    동일하게 lifespan 생애주기에 묶어야 하기 때문이다.
    """
    return request.state.generate_semaphore


class GeneratePayloadRequest(BaseModel):
    isbn: str


class GenerateBulkRequest(BaseModel):
    isbns: list[str]

    @field_validator("isbns")
    @classmethod
    def check_limit(cls, value: list[str]) -> list[str]:
        if len(value) == 0:
            raise ValueError("ISBN 목록이 비어 있습니다.")
        if len(value) > 10:
            raise ValueError("한 번에 최대 10개까지 생성할 수 있습니다.")
        return value


@router.post("/generate", response_model=GenerateResult)
@router.post("/generate/marc", response_model=GenerateResult)
async def generate_marc(
    body: GeneratePayloadRequest,
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> "GenerateResultType":
    """ISBN 조회 후 LLM을 호출해 GenerateResult JSON을 반환한다."""
    try:
        lookup_result = await lookup_one(http_client, body.isbn)
    except ValueError as exc:
        logger.warning("ISBN 형식 오류: isbn=%s error=%s", body.isbn, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not lookup_result["found"]:
        logger.warning("서지정보 조회 실패: isbn=%s", lookup_result["isbn"])
        raise HTTPException(
            status_code=404,
            detail=f"ISBN {lookup_result['isbn']} 에 해당하는 서지정보를 찾을 수 없습니다.",
        )

    lookup_model = LookupResponseSchema.model_validate(lookup_result)
    llm_input = build_llm_input(lookup_model)
    try:
        generated = await generate_marc_result(llm_input)
    except LLMClientError as exc:
        logger.warning("MARC 생성 실패(LLM 오류): isbn=%s error=%s", body.isbn, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except OutputValidationError as exc:
        logger.warning("MARC 생성 실패(출력 검증 오류): isbn=%s error=%s", body.isbn, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return cast("GenerateResultType", generated)


async def _generate_one(http_client: httpx.AsyncClient, sem: asyncio.Semaphore, isbn: str) -> dict[str, Any]:
    """단건 generate_marc와 동일한 파이프라인을 실행하되, 실패를 예외로 던지지 않고 결과로 반환한다."""
    async with sem:
        try:
            lookup_result = await lookup_one(http_client, isbn)
        except ValueError as exc:
            logger.warning("다건 생성 중 ISBN 형식 오류: isbn=%s error=%s", isbn, exc)
            return {"isbn": isbn, "status": "error", "error_code": "invalid_isbn", "error_message": str(exc)}

        if not lookup_result["found"]:
            logger.warning("다건 생성 중 서지정보 조회 실패: isbn=%s", lookup_result["isbn"])
            return {
                "isbn": lookup_result["isbn"],
                "status": "error",
                "error_code": "not_found",
                "error_message": f"ISBN {lookup_result['isbn']} 에 해당하는 서지정보를 찾을 수 없습니다.",
            }

        lookup_model = LookupResponseSchema.model_validate(lookup_result)
        llm_input = build_llm_input(lookup_model)
        try:
            generated = await generate_marc_result(llm_input)
        except LLMClientError as exc:
            logger.warning("다건 생성 중 MARC 생성 실패(LLM 오류): isbn=%s error=%s", isbn, exc)
            return {
                "isbn": lookup_result["isbn"],
                "status": "error",
                "error_code": "llm_error",
                "error_message": str(exc),
            }
        except OutputValidationError as exc:
            logger.warning("다건 생성 중 MARC 생성 실패(출력 검증 오류): isbn=%s error=%s", isbn, exc)
            return {
                "isbn": lookup_result["isbn"],
                "status": "error",
                "error_code": "validation_error",
                "error_message": str(exc),
            }

        return {"isbn": lookup_result["isbn"], "status": "success", "result": generated.model_dump()}


@router.post("/generate/marc/bulk")
async def generate_marc_bulk(
    body: GenerateBulkRequest,
    http_client: httpx.AsyncClient = Depends(get_http_client),
    sem: asyncio.Semaphore = Depends(get_generate_semaphore),
) -> dict[str, Any]:
    """여러 ISBN을 각각 조회+생성한다. 한 책의 실패가 다른 책 처리를 막지 않는다."""
    results = await asyncio.gather(*(_generate_one(http_client, sem, isbn) for isbn in body.isbns))
    return {"total": len(results), "results": results}
