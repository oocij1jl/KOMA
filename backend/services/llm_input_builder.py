from __future__ import annotations

from typing import TYPE_CHECKING

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas.llm import LLMInputPayload
    from backend.schemas.lookup import LookupResponseSchema
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    import importlib

    LLMInputPayload = importlib.import_module("schemas.llm").LLMInputPayload
    LookupResponseSchema = importlib.import_module("schemas.lookup").LookupResponseSchema

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.llm import LLMInputPayload as LLMInputPayloadType
    from backend.schemas.lookup import LookupResponseSchema as LookupResponseSchemaType


def build_llm_input(lookup_result: "LookupResponseSchemaType") -> "LLMInputPayloadType":
    """lookup 결과를 LLM 입력 봉투로 조립한다."""

    # NOTE: 이번 단계에서는 BiblioSchema 전체를 facts로 재사용한다.
    # 다음 단계에서 facts-only 기준으로 축소 예정이며,
    # cover_url / toc_url / intro_url 는 생성 근거가 아니므로 재검토 대상이다.
    return LLMInputPayload(
        isbn=lookup_result.isbn,
        biblio=lookup_result.biblio,
        evidence=lookup_result.evidence,
    )
