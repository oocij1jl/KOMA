from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas import llm as llm_schema
    from backend.schemas import llm_output as llm_output_schema
    from backend.clients import llm_client
    from backend.services import output_validator as output_validator_service
    from backend.services import rag_loader as rag_loader_service
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    llm_schema = importlib.import_module("schemas.llm")
    llm_output_schema = importlib.import_module("schemas.llm_output")
    llm_client = importlib.import_module("clients.llm_client")
    output_validator_service = importlib.import_module("services.output_validator")
    rag_loader_service = importlib.import_module("services.rag_loader")

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.llm import LLMInputPayload as LLMInputPayloadType
    from backend.schemas.llm_output import GenerateResult as GenerateResultType

LLMInputPayload = cast(type["LLMInputPayloadType"], llm_schema.LLMInputPayload)
load_rules: Callable[[list[str]], dict[str, str]] = rag_loader_service.load_rules
GenerateResult = llm_output_schema.GenerateResult
validate_output: Callable[[str], "GenerateResultType"] = output_validator_service.validate_output


FIELD_653_EXAMPLE = {
    "tag": "653",
    "source": "ai_inference",
    "indicator1": " ",
    "indicator2": " ",
    "subfields": [
        {"code": "a", "value": "진화론"},
        {"code": "a", "value": "생물학"},
    ],
    "review_required": True,
    "confidence": "medium",
    "note": "정보나루 키워드 기반 비통제 색인어. 사서 검수 필요",
    "evidence": {
        "from": ["keywords"],
        "keywords_used": ["진화론(0.92)", "생물학(0.81)"],
        "reasoning": "가중치 상위 키워드를 의미 변경 없이 최소 정제하여 653으로 제안",
    },
}

GENERATE_RESULT_EXAMPLE = {
    "fields": [FIELD_653_EXAMPLE],
    "skipped_fields": [
        {
            "tag": "650",
            "reason": "통제 주제명은 표목표 대조 필요",
        }
    ],
    "warnings": ["653 색인어는 키워드 기반 추론 — 반드시 검수"],
}


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def select_generation_tags(payload: "LLMInputPayloadType") -> list[str]:
    """payload.generate_options에서 실제 생성 대상 tag를 고른다."""

    options = payload.generate_options
    skipped = set(options.skipped_by_default)
    candidates = [
        *options.required_fields,
        *options.review_required_fields,
        *options.conditional_fields,
    ]
    return _dedupe_preserve_order([tag for tag in candidates if tag not in skipped])


def _format_rules(rules_by_tag: dict[str, str]) -> str:
    if not rules_by_tag:
        return "제공된 생성 대상 tag 중 로드된 RAG 규칙이 없습니다. 규칙이 없는 필드는 payload와 constraints만 따른다."

    sections: list[str] = []
    for tag in sorted(rules_by_tag):
        sections.append(f"## tag {tag}\n{rules_by_tag[tag]}")
    return "\n\n".join(sections)


def _format_constraints(constraints: list[str]) -> str:
    lines = [f"{index}. {constraint}" for index, constraint in enumerate(constraints, start=1)]
    return "\n".join(lines)


def _format_650_skip_instruction(payload: "LLMInputPayloadType") -> str:
    if "650" not in payload.generate_options.skipped_by_default:
        return ""
    return (
        "650은 skipped_by_default에 있으므로 생성하지 않는다. "
        "반드시 skipped_fields에 tag='650'과 reason='통제 주제명은 표목표 대조 필요'를 남긴다."
    )


def _format_field_evidence_map(payload: "LLMInputPayloadType") -> dict[str, list[str]]:
    return {
        tag: entry.evidence_sources
        for tag, entry in payload.field_evidence_map.items()
    }


def build_prompt(payload: "LLMInputPayloadType") -> str:
    """LLMInputPayload와 RAG 규칙을 합쳐 LLM 호출 직전 프롬프트 문자열을 만든다.

    이 함수는 프롬프트 문자열만 반환하며 OpenAI/Gemini/Anthropic 등 어떤 LLM 호출도 하지 않는다.
    """

    generation_tags = select_generation_tags(payload)
    rules_by_tag = load_rules(generation_tags)
    schema = GenerateResult.model_json_schema()
    biblio_json = payload.biblio.model_dump(mode="json")
    evidence_json = payload.evidence.model_dump(mode="json")
    field_evidence_map_json = _format_field_evidence_map(payload)

    return "\n\n".join(
        [
            "[SYSTEM]\n"
            + "너는 KORMARC 목록 레코드 생성기다. 주어진 규칙과 근거(evidence)만으로 생성하고, "
            + "근거가 없으면 필드를 만들지 마라. MARC 문자열이 아니라 지정된 JSON 구조로만 답하라.",
            "[CONSTRAINTS]\n"
            + f"payload.constraints {len(payload.constraints)}개를 그대로 적용한다.\n"
            + f"{_format_constraints(payload.constraints)}\n\n"
            + "constraints_json:\n"
            + f"{_dump_json(payload.constraints)}",
            "[BIBLIO + EVIDENCE]\n"
            + "raw 원문 응답은 포함하지 않는다. evidence.available 및 translation_signals를 반드시 확인한다.\n"
            + f"biblio:\n{_dump_json(biblio_json)}\n\n"
            + f"evidence:\n{_dump_json(evidence_json)}",
            "[FIELD_EVIDENCE_MAP: 각 필드에 사용 가능한 evidence 소스]\n"
            + "이 섹션은 어떤 evidence 소스를 어떤 필드에 사용할 수 있는지만 정의한다. "
            + "필드 값을 만드는 방법은 아래 RAG 규칙 섹션을 따른다.\n"
            + f"{_dump_json(field_evidence_map_json)}",
            "[GENERATION TAGS]\n"
            + f"생성 대상 tag: {_dump_json(generation_tags)}\n"
            + f"skipped_by_default: {_dump_json(payload.generate_options.skipped_by_default)}\n"
            + f"{_format_650_skip_instruction(payload)}",
            "[RAG RULES: 각 필드를 만드는 방법]\n"
            + "이 섹션은 field_evidence_map의 evidence 소스를 사용해 값을 만드는 방법만 설명한다. "
            + "사용 가능한 evidence 소스를 재정의하지 않는다.\n"
            + f"{_format_rules(rules_by_tag)}",
            "[OUTPUT FORMAT]\n"
            + "반드시 GenerateResult JSON 객체 하나로만 답한다. Markdown, MARC 문자열, 설명 문장을 출력하지 않는다. "
            + "키명은 indicator1 / indicator2를 사용하고 ind1 / ind2는 사용하지 않는다. "
            + "source='ai_inference' 필드는 evidence 객체를 반드시 포함한다.\n"
            + f"GenerateResult JSON Schema:\n{_dump_json(schema)}\n\n"
            + f"653 출력 예시를 포함한 GenerateResult 예시:\n{_dump_json(GENERATE_RESULT_EXAMPLE)}",
        ]
    )


async def generate_marc(payload: "LLMInputPayloadType") -> "GenerateResultType":
    """프롬프트 생성, LLM 호출, 출력 검증을 묶어 GenerateResult를 반환한다."""

    prompt = build_prompt(payload)
    raw_output = await llm_client.generate(prompt)
    return validate_output(raw_output)
