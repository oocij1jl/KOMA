import importlib
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, Field

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas import lookup as lookup_schema
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    lookup_schema = importlib.import_module("schemas.lookup")

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.lookup import BiblioSchema as BiblioSchemaType
    from backend.schemas.lookup import EvidenceSchema as EvidenceSchemaType

BiblioSchema = cast(type["BiblioSchemaType"], lookup_schema.BiblioSchema)
EvidenceSchema = cast(type["EvidenceSchemaType"], lookup_schema.EvidenceSchema)


class GenerateOptions(BaseModel):
    required_fields: list[str] = Field(default_factory=lambda: ["020", "245", "260", "700", "710"])
    review_required_fields: list[str] = Field(default_factory=lambda: ["653", "056", "082"])
    conditional_fields: list[str] = Field(
        default_factory=lambda: ["041", "246", "250", "300", "490", "500", "546", "830", "950"]
    )
    skipped_by_default: list[str] = Field(default_factory=lambda: ["650"])
    allow_inference: bool = True
    show_source: bool = True


class FieldEvidenceMapEntry(BaseModel):
    evidence_sources: list[str] = Field(default_factory=list)
    skip_allowed: bool = True
    rag_notes: str = "RAG: 팀원1"


class LLMInputPayload(BaseModel):
    isbn: str = Field(pattern=r"^\d{13}$")
    biblio: "BiblioSchemaType"
    evidence: "EvidenceSchemaType"
    generate_options: GenerateOptions = Field(default_factory=GenerateOptions)
    constraints: list[str] = Field(
        default_factory=lambda: [
            '빈 값은 "" 를 사용하고 null은 사용하지 않는다.',
            "value에는 구두점을 넣지 않는다. 구두점은 후처리 단계 책임이다.",
            "available=false 인 evidence 소스는 추론 근거로 사용하지 않는다.",
            "LLM 입력에는 raw 원문 응답을 포함하지 않는다.",
        ]
    )
    # field_evidence_map은 추론/판단이 필요한 필드만 다룬다.
    # biblio 값을 거의 그대로 옮기는 직역형 조건부 필드(246/250/300/490/830/950)는 map에서 제외한다.
    field_evidence_map: dict[str, FieldEvidenceMapEntry] = Field(
        default_factory=lambda: {
            "653": FieldEvidenceMapEntry(evidence_sources=["keywords", "description", "co_loan_books"]),
            "650": FieldEvidenceMapEntry(
                evidence_sources=[],
                skip_allowed=True,
                rag_notes="MVP 기본 skip — 통제 주제명은 표목표 대조 필요: 653으로 대체",
            ),
            "056": FieldEvidenceMapEntry(evidence_sources=["keywords", "kdc_from_api", "description"]),
            "082": FieldEvidenceMapEntry(evidence_sources=["keywords", "ddc_from_api", "description"]),
            "546": FieldEvidenceMapEntry(evidence_sources=["description", "title", "author"]),
            "041": FieldEvidenceMapEntry(evidence_sources=["translation_signals", "description", "author"]),
            "500": FieldEvidenceMapEntry(evidence_sources=["translation_signals", "description", "author"]),
        }
    )

    # TODO: 다음 단계에서 biblio는 facts-only 기준으로 축소 예정
    # TODO: biblio.found는 조회 상태값이므로 facts-only 축소 시 제외 대상
    # cover_url / toc_url / intro_url 는 생성 근거가 아니므로 builder 단계에서 재검토
    # TODO: subject가 대분류 한 자리(예: "8")만 오는 경우(국중도 KDC 공백 시) kdc와 redundant하므로 정제 검토


_ = LLMInputPayload.model_rebuild(
    _types_namespace={
        "BiblioSchemaType": BiblioSchema,
        "EvidenceSchemaType": EvidenceSchema,
    }
)
