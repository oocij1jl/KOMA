from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubfieldItem(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9]$")
    value: str


class FieldEvidence(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    from_: list[str] = Field(alias="from")
    keywords_used: list[str] = Field(default_factory=list)
    reasoning: str


class GeneratedField(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"source": {"const": "ai_inference"}}},
                    "then": {
                        "required": ["evidence"],
                        "properties": {"evidence": {"not": {"type": "null"}}},
                    },
                }
            ]
        }
    )

    tag: str = Field(pattern=r"^\d{3}$")
    source: Literal["api", "ai_inference"]
    indicator1: str = Field(min_length=1, max_length=1)
    indicator2: str = Field(min_length=1, max_length=1)
    subfields: list[SubfieldItem] = Field(min_length=1)
    review_required: bool
    confidence: Literal["high", "medium", "low"]
    # source="ai_inference"이면 evidence 필수다. 강제 검증은 다음 단계 validator 책임이다.
    evidence: FieldEvidence | None = None
    note: str = ""

    @model_validator(mode="after")
    def validate_evidence_for_ai_inference(self) -> "GeneratedField":
        if self.source == "ai_inference" and self.evidence is None:
            raise ValueError("source='ai_inference' requires evidence")
        return self


class SkippedField(BaseModel):
    tag: str = Field(pattern=r"^\d{3}$")
    reason: str


class GenerateResult(BaseModel):
    fields: list[GeneratedField]
    skipped_fields: list[SkippedField]
    warnings: list[str]
