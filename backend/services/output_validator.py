from __future__ import annotations

import importlib
import json
import re
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas import lookup as lookup_schema
    from backend.schemas import llm_output as llm_output_schema
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    lookup_schema = importlib.import_module("schemas.lookup")
    llm_output_schema = importlib.import_module("schemas.llm_output")

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.lookup import BiblioSchema as BiblioSchemaType
    from backend.schemas.lookup import EvidenceSchema as EvidenceSchemaType
    from backend.schemas.llm_output import GenerateResult as GenerateResultType
    from backend.schemas.llm_output import GeneratedField as GeneratedFieldType
    from backend.schemas.llm_output import SkippedField as SkippedFieldType

BiblioSchema = cast(type["BiblioSchemaType"], lookup_schema.BiblioSchema)
EvidenceSchema = cast(type["EvidenceSchemaType"], lookup_schema.EvidenceSchema)
GenerateResult = cast(type["GenerateResultType"], llm_output_schema.GenerateResult)
GeneratedField = cast(type["GeneratedFieldType"], llm_output_schema.GeneratedField)
SkippedField = cast(type["SkippedFieldType"], llm_output_schema.SkippedField)


class OutputValidationError(ValueError):
    """LLM 출력 JSON이 GenerateResult 계약을 만족하지 못할 때 사용한다."""


STRUCTURAL_PUNCTUATION_RE = re.compile(r"(^[▼$/ ]+|[ ]*[:;/]+$)")
FIELD_650_SKIP_REASON = "통제 주제명은 표목표 대조 필요: 653으로 대체"
FIELD_653_SKIP_REASON = "주제 색인어로 사용할 독립 근거 부족"
FIELD_300_SKIP_REASON = "형태사항 근거 부족"
FIELD_056_SKIP_REASON = "KDC 근거 부족: 056 생성 보류"
FIELD_082_SKIP_REASON = "DDC 근거 부족: 082 생성 보류"
AUTHOR_SPLIT_RE = re.compile(r"\s*(?:[·/,;:]|\band\b|&)\s*", re.IGNORECASE)
_AUTHOR_ROLE_WORDS = "지은이|옮긴이|엮은이|번역|편저|공저|감수|편집|지음|옮김|저자|엮음|그림|사진|글|씀|저|역"
AUTHOR_ROLE_RE = re.compile(rf"(?:^|\s)(?:{_AUTHOR_ROLE_WORDS})(?=\s|$)")
BRACKETED_TEXT_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
WHITESPACE_RE = re.compile(r"\s+")
MEANINGLESS_300_A_RE = re.compile(r"^0(?:\s*p\.?|p\.?)?$", re.IGNORECASE)
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


def _comparison_key(value: str) -> str:
    normalized, _ = _normalize_value(value)
    normalized = BRACKETED_TEXT_RE.sub(" ", normalized)
    normalized = WHITESPACE_RE.sub("", normalized)
    return normalized.casefold()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _extract_author_names(author: str) -> list[str]:
    cleaned_author = BRACKETED_TEXT_RE.sub(" ", author).strip()
    if not cleaned_author:
        return []

    raw_parts = AUTHOR_SPLIT_RE.split(cleaned_author)
    if len(raw_parts) == 1:
        raw_parts = [cleaned_author]

    extracted: list[str] = []
    for raw_part in raw_parts:
        candidate = AUTHOR_ROLE_RE.sub(" ", raw_part)
        candidate = WHITESPACE_RE.sub(" ", candidate).strip()
        if candidate:
            extracted.append(candidate)

    return _dedupe_preserve_order(extracted)


def _build_title_like_candidates(biblio: "BiblioSchemaType | None", evidence: "EvidenceSchemaType | None") -> list[str]:
    candidates: list[str] = []
    if biblio is not None:
        candidates.extend([biblio.title, biblio.series_title, biblio.publisher])
    if evidence is not None:
        candidates.extend(book.bookname for book in evidence.co_loan_books)
    return [candidate for candidate in _dedupe_preserve_order(candidates) if _comparison_key(candidate)]


def _build_exact_match_candidates(biblio: "BiblioSchemaType | None") -> list[str]:
    candidates: list[str] = []
    if biblio is not None:
        candidates.append(biblio.publisher)
    return [candidate for candidate in _dedupe_preserve_order(candidates) if _comparison_key(candidate)]


def _build_author_candidates(biblio: "BiblioSchemaType | None") -> list[str]:
    if biblio is None:
        return []
    candidates = _extract_author_names(biblio.author)
    return [candidate for candidate in _dedupe_preserve_order(candidates) if _comparison_key(candidate)]


def _matches_title_like_candidate(term: str, candidates: list[str]) -> bool:
    term_key = _comparison_key(term)
    if not term_key:
        return False
    for candidate in candidates:
        candidate_key = _comparison_key(candidate)
        if candidate_key and (term_key == candidate_key or term_key in candidate_key or candidate_key in term_key):
            return True
    return False


def _matches_exact_candidate(term: str, candidates: list[str]) -> bool:
    term_key = _comparison_key(term)
    if not term_key:
        return False
    return any(term_key == _comparison_key(candidate) for candidate in candidates)


def _matches_author_candidate(term: str, candidates: list[str]) -> bool:
    term_variants = {_comparison_key(term)}
    term_variants.update(_comparison_key(candidate) for candidate in _extract_author_names(term))
    term_variants.discard("")
    if not term_variants:
        return False

    candidate_keys = {_comparison_key(candidate) for candidate in candidates}
    candidate_keys.discard("")
    return any(term_variant in candidate_keys for term_variant in term_variants)


def _remove_skip_tag(skipped_fields: list["SkippedFieldType"], tag: str) -> None:
    skipped_fields[:] = [item for item in skipped_fields if item.tag != tag]


def _set_skip_reason(skipped_fields: list["SkippedFieldType"], tag: str, reason: str) -> None:
    for item in skipped_fields:
        if item.tag == tag:
            item.reason = reason
            return
    skipped_fields.append(SkippedField(tag=tag, reason=reason))


def _remove_redundant_653_fields(
    fields: list["GeneratedFieldType"],
    skipped_fields: list["SkippedFieldType"],
    *,
    biblio: "BiblioSchemaType | None",
    evidence: "EvidenceSchemaType | None",
) -> list["GeneratedFieldType"]:
    if biblio is None and evidence is None:
        return fields

    title_like_candidates = _build_title_like_candidates(biblio, evidence)
    exact_match_candidates = _build_exact_match_candidates(biblio)
    author_candidates = _build_author_candidates(biblio)
    if not title_like_candidates and not exact_match_candidates and not author_candidates:
        return fields

    kept_fields: list["GeneratedFieldType"] = []
    had_653_fields = False
    retained_any_653 = False
    for field in fields:
        if field.tag != "653":
            kept_fields.append(field)
            continue

        had_653_fields = True

        kept_subfields = []
        for subfield in field.subfields:
            if subfield.code != "a":
                kept_subfields.append(subfield)
                continue

            if _matches_title_like_candidate(subfield.value, title_like_candidates):
                continue
            if _matches_exact_candidate(subfield.value, exact_match_candidates):
                continue
            if _matches_author_candidate(subfield.value, author_candidates):
                continue

            kept_subfields.append(subfield)

        if any(subfield.code == "a" for subfield in kept_subfields):
            field.subfields = kept_subfields
            kept_fields.append(field)
            retained_any_653 = True
            continue

    if retained_any_653:
        _remove_skip_tag(skipped_fields, "653")
    elif had_653_fields:
        _set_skip_reason(skipped_fields, "653", FIELD_653_SKIP_REASON)

    return kept_fields


def _remove_650_fields(
    fields: list["GeneratedFieldType"], skipped_fields: list["SkippedFieldType"]
) -> tuple[list["GeneratedFieldType"], bool]:
    kept_fields = [field for field in fields if field.tag != "650"]
    removed = len(kept_fields) != len(fields)
    if removed and not any(item.tag == "650" for item in skipped_fields):
        skipped_fields.append(SkippedField(tag="650", reason=FIELD_650_SKIP_REASON))
    return kept_fields, removed


def _cleanup_structural_field_errors(
    fields: list["GeneratedFieldType"],
    skipped_fields: list["SkippedFieldType"],
    warnings: list[str],
) -> list["GeneratedFieldType"]:
    kept_fields: list["GeneratedFieldType"] = []

    for field in fields:
        if field.tag == "020":
            kept_subfields = []
            removed_invalid_supplement = False

            for subfield in field.subfields:
                if subfield.code in {"a", "c"}:
                    kept_subfields.append(subfield)
                    continue

                if subfield.value.isdigit():
                    kept_subfields.append(subfield)
                    continue

                removed_invalid_supplement = True

            if removed_invalid_supplement:
                warnings.append("020 부가기호 비정상값 제거됨")

            if kept_subfields:
                field.subfields = kept_subfields
                kept_fields.append(field)
            else:
                _set_skip_reason(skipped_fields, "020", "식별기호가 없어 생성 제외")

            continue

        if field.tag == "300":
            kept_subfields = []
            removed_meaningless_page = False

            for subfield in field.subfields:
                if subfield.code == "a" and (
                    subfield.value == "" or MEANINGLESS_300_A_RE.fullmatch(subfield.value) is not None
                ):
                    removed_meaningless_page = True
                    continue

                kept_subfields.append(subfield)

            if removed_meaningless_page:
                warnings.append("300 페이지 정보 무의미값 제거됨")

            if kept_subfields:
                field.subfields = kept_subfields
                kept_fields.append(field)
            else:
                _set_skip_reason(skipped_fields, "300", FIELD_300_SKIP_REASON)

            continue

        if field.tag == "056":
            a_values = [subfield.value for subfield in field.subfields if subfield.code == "a"]
            if not a_values or all(value in {"", "000"} for value in a_values):
                if any(value == "000" for value in a_values):
                    warnings.append("056 KDC 기본값 000 제거됨")
                else:
                    warnings.append("056 KDC 빈값 제거됨")
                _set_skip_reason(skipped_fields, "056", FIELD_056_SKIP_REASON)
                continue

        if field.tag == "082":
            a_values = [subfield.value for subfield in field.subfields if subfield.code == "a"]
            if a_values and all(value == "000" for value in a_values):
                warnings.append("082 DDC 기본값 000 제거됨")
                _set_skip_reason(skipped_fields, "082", FIELD_082_SKIP_REASON)
                continue

        kept_fields.append(field)

    return kept_fields


def validate_output(
    raw_output: str,
    *,
    biblio: "BiblioSchemaType | None" = None,
    evidence: "EvidenceSchemaType | None" = None,
) -> "GenerateResultType":
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
    if any(item.tag == "650" for item in skipped_fields):
        _set_skip_reason(skipped_fields, "650", FIELD_650_SKIP_REASON)
    fields, removed_650 = _remove_650_fields(list(result.fields), skipped_fields)
    if removed_650:
        warnings.append("650은 기본 skip 정책이므로 fields에서 제거했습니다.")

    for field in fields:
        for subfield in field.subfields:
            normalized, changed = _normalize_value(subfield.value)
            if changed:
                warnings.append(f"{field.tag}${subfield.code} 값의 구두점을 제거했습니다.")
                subfield.value = normalized

    fields = _cleanup_structural_field_errors(fields, skipped_fields, warnings)
    fields = _remove_redundant_653_fields(fields, skipped_fields, biblio=biblio, evidence=evidence)

    return GenerateResult(fields=fields, skipped_fields=skipped_fields, warnings=warnings)
