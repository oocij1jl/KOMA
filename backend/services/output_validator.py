from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas.llm_output import GenerateResult, GeneratedField, SkippedField
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from schemas.llm_output import GenerateResult, GeneratedField, SkippedField


class OutputValidationError(ValueError):
    """LLM 출력 JSON이 GenerateResult 계약을 만족하지 못할 때 사용한다."""


STRUCTURAL_PUNCTUATION_RE = re.compile(r"(^[▼$/ ]+|[ ]*[:;/]+$)")
FIELD_650_SKIP_REASON = "통제 주제명은 표목표 대조 필요: 653으로 대체"
API_SOURCE_ALIASES = {
    "d4l",
    "data4library",
    "data4library.kr",
    "nl",
    "nl.go.kr",
    "national_library",
}
BIBLIO_API_TAGS = {"020", "245", "260", "700", "710"}


def _load_json_object(raw_output: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise OutputValidationError(f"LLM 응답 JSON 파싱 실패: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise OutputValidationError("LLM 응답은 JSON 객체여야 합니다.")
    return parsed


def _normalize_source_aliases(parsed: dict[str, Any]) -> None:
    fields = parsed.get("fields")
    if not isinstance(fields, list):
        return

    for field in fields:
        if not isinstance(field, dict):
            continue
        source = field.get("source")
        if isinstance(source, str) and source.lower() in API_SOURCE_ALIASES:
            field["source"] = "api"


def _ensure_skipped_fields(parsed: dict[str, Any]) -> list[dict[str, str]]:
    skipped_fields = parsed.get("skipped_fields")
    if not isinstance(skipped_fields, list):
        skipped_fields = []
        parsed["skipped_fields"] = skipped_fields
    return skipped_fields


def _append_skip_once(skipped_fields: list[dict[str, str]], tag: str, reason: str) -> None:
    if not any(isinstance(item, dict) and item.get("tag") == tag for item in skipped_fields):
        skipped_fields.append({"tag": tag, "reason": reason})


def _preprocess_policy_violations(parsed: dict[str, Any]) -> None:
    fields = parsed.get("fields")
    if not isinstance(fields, list):
        return

    skipped_fields = _ensure_skipped_fields(parsed)
    kept_fields: list[Any] = []

    for field in fields:
        if not isinstance(field, dict):
            continue

        tag = field.get("tag")
        subfields = field.get("subfields")
        if isinstance(tag, str) and isinstance(subfields, list) and len(subfields) == 0:
            _append_skip_once(skipped_fields, tag, "식별기호가 없어 생성 제외")
            continue

        source = field.get("source")
        evidence = field.get("evidence")
        if source == "ai_inference" and not evidence:
            if tag in BIBLIO_API_TAGS:
                field["source"] = "api"
            elif isinstance(tag, str):
                _append_skip_once(skipped_fields, tag, "근거 없는 추론: evidence 누락")
                continue

        kept_fields.append(field)

    parsed["fields"] = kept_fields


def _normalize_value(value: str) -> tuple[str, bool]:
    normalized = STRUCTURAL_PUNCTUATION_RE.sub("", value).strip()
    normalized = normalized.replace("▼", "").strip()
    return normalized, normalized != value


def _remove_650_fields(fields: list[GeneratedField], skipped_fields: list[SkippedField]) -> tuple[list[GeneratedField], bool]:
    kept_fields = [field for field in fields if field.tag != "650"]
    removed = len(kept_fields) != len(fields)
    if removed and not any(item.tag == "650" for item in skipped_fields):
        skipped_fields.append(SkippedField(tag="650", reason=FIELD_650_SKIP_REASON))
    return kept_fields, removed


def validate_output(raw_output: str) -> GenerateResult:
    """LLM JSON 문자열을 GenerateResult로 검증하고 정책 위반을 보정한다."""

    parsed = _load_json_object(raw_output)
    _normalize_source_aliases(parsed)
    _preprocess_policy_violations(parsed)
    try:
        result = GenerateResult.model_validate(parsed)
    except ValidationError as exc:
        raise OutputValidationError(f"LLM 출력 스키마 검증 실패: {exc}") from exc

    skipped_fields = list(result.skipped_fields)
    warnings = list(result.warnings)
    fields, removed_650 = _remove_650_fields(list(result.fields), skipped_fields)
    if removed_650:
        warnings.append("650은 기본 skip 정책이므로 fields에서 제거했습니다.")

    for field in fields:
        for subfield in field.subfields:
            normalized, changed = _normalize_value(subfield.value)
            if changed:
                warnings.append(f"{field.tag}${subfield.code} 값의 구두점을 제거했습니다.")
                subfield.value = normalized

    return GenerateResult(fields=fields, skipped_fields=skipped_fields, warnings=warnings)
