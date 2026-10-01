from __future__ import annotations

import importlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

logger = logging.getLogger(__name__)

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
        logger.warning("LLM 응답 JSON 파싱 실패: %s", exc.msg)
        raise OutputValidationError(f"LLM 응답 JSON 파싱 실패: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        logger.warning("LLM 응답이 JSON 객체가 아님: type=%s", type(parsed).__name__)
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


def _assign_generated_by(parsed: dict[str, Any]) -> None:
    """LLM 출력에서 온 필드는 모두 generated_by="llm"이다.

    이 함수는 LLM 응답만 다룬다. 규칙 레이어(deterministic_fields)가 만든 필드는
    이 경로를 거치지 않고 자기 값("rule")을 그대로 가진다. 예전에는 태그가
    BIBLIO_API_TAGS에 있으면 "api"로 표기했지만, 실제 생성 주체가 아니라
    태그만 보고 붙이는 라벨이라 검수자와 평가를 오도했다.
    """
    fields = parsed.get("fields")
    if not isinstance(fields, list):
        return

    for field in fields:
        if not isinstance(field, dict):
            continue
        field["generated_by"] = "llm"


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


def _matches_title_like_candidate(term: str, candidates: list[str], *, independently_supported: bool = False) -> bool:
    """서지 값과 겹치는 653 색인어를 거른다.

    입력 키워드에 그대로 있는 주제어는 독립 근거가 있으므로, 출판사 '길'이
    키워드 '길찾기'에 들어 있다는 식의 부분 문자열 겹침으로 지우지 않는다.
    서명·총서명·출판사명을 그대로 복사한 값만 제외한다.
    """
    term_key = _comparison_key(term)
    if not term_key:
        return False
    for candidate in candidates:
        candidate_key = _comparison_key(candidate)
        if not candidate_key:
            continue
        if independently_supported:
            if candidate_key == term_key:
                return True
        elif candidate_key in term_key or term_key in candidate_key:
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

    keyword_keys = (
        {_comparison_key(item.word) for item in evidence.keywords}
        if evidence is not None and evidence.available.keywords
        else set()
    )

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

            if _matches_title_like_candidate(
                subfield.value,
                title_like_candidates,
                independently_supported=_comparison_key(subfield.value) in keyword_keys,
            ):
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


FIELD_041_SKIP_REASON = "번역·다국어 근거 없음: 041 생성 보류"
FIELD_546_SKIP_REASON = "언어주기 근거 없음: 단일 언어 추정만으로 생성 금지"
# This is a bounded service vocabulary, not a language detector. Unknown names
# are deferred; explicitly labelled three-letter source codes remain usable.
_LANGUAGE_CODES = {
    "한국어": "kor",
    "영어": "eng",
    "독일어": "ger",
    "스페인어": "spa",
    "일본어": "jpn",
    "중국어": "chi",
    "프랑스어": "fre",
}
_LANGUAGE_TOKEN = "|".join(_LANGUAGE_CODES) + r"|(?<![A-Za-z])[a-z]{3}(?![A-Za-z])"
_LANGUAGE_MENTION_RE = re.compile(_LANGUAGE_TOKEN)
# 역할 표지 뒤에 흔한 조사("원작은 영어", "본문은 한국어")와 "원작 언어: eng"
# 형태를 함께 받는다. '의'는 "원작의 언어"처럼 '언어'가 뒤따를 때만 역할
# 표지다. "원작의 한국어 번역본"의 한국어는 원작 언어가 아니라 번역어다.
_ROLE_PREFIX_TAIL = r"(?:(?:\s*의)?\s*언어)?\s*(?:은|는|이|가)?\s*[:：=]?\s*$"
_ROLE_SUFFIX_PARTICLE = r"(?:이|가|은|는|의|을|를)?\s*"
_LANGUAGE_ROLES = {
    "a": (
        rf"(?:본문|번역문|번역본){_ROLE_PREFIX_TAIL}",
        r"(?:로|으로)?\s*(?:번역|옮긴|옮겨|옮김)",
    ),
    "b": (rf"(?:요약|요약문|초록){_ROLE_PREFIX_TAIL}", rf"{_ROLE_SUFFIX_PARTICLE}(?:요약|초록)"),
    "f": (rf"(?:목차|내용목차){_ROLE_PREFIX_TAIL}", rf"{_ROLE_SUFFIX_PARTICLE}목차"),
    "h": (
        rf"(?:원작|원저작|원저|원문|원서|원본){_ROLE_PREFIX_TAIL}",
        rf"{_ROLE_SUFFIX_PARTICLE}(?:원작|원저|원문|원서|원본)",
    ),
    "k": (rf"중역{_ROLE_PREFIX_TAIL}", rf"{_ROLE_SUFFIX_PARTICLE}중역"),
}
_MULTILINGUAL_RE = re.compile(
    rf"(?:{_LANGUAGE_TOKEN})(?:\s*(?:와|과|및|/|·|,)\s*(?:{_LANGUAGE_TOKEN}))+"
    r"\s*(?:를|을|로|으로|가|이)?\s*(?:대역|병기|본문)"
)
_LANGUAGE_NOTE_KEYWORDS = ("번역", "원작", "원저", "원서", "옮김", "대역", "병기", "자막", "요약", "초록", "원문", "목차", "중역")
_GENERIC_TRANSLATION_NOTES = {"번역서", "번역 자료", "번역된 자료"}
# 의역 경로는 언어 관계와 조사·연결어로만 이루어진 주기에 한정한다.
# 언어 쌍이 맞는다는 이유로 "점자 수록", "원문 삭제", "무료 제공" 같은
# 별개 주장을 통과시키지 않는다. 그 밖의 주기는 원문 전사 경로로 확인한다.
_NOTE_PARAPHRASE_RE = re.compile(
    r"(?:원저작|원작|원저|원문|원서|원본|본문|번역문|번역본|번역서|번역|"
    r"옮긴|옮겨|옮김|언어|대역|병기|요약문|요약|초록|내용목차|목차|중역|"
    r"입니다|이다|이며|이고|임|으로|에서|로|의|은|는|이|가|을|를|와|과|및|"
    r"하였|했|하여|되어|된|한|함|다|책|자료|[\s,;:.·/()\[\]])+"
)
_CLAUSE_SPLIT_RE = re.compile(r"[.!?;\n]")
# 부정·불확실 판정은 언어·번역 주장에만 적용한다. '빠짐없이'처럼 긍정 서술을
# 꾸미는 '없이'는 부정이 아니므로 제외한다.
_LANGUAGE_CLAIM_TOKEN_RE = re.compile(
    rf"(?:{_LANGUAGE_TOKEN})|번역|원작|원저|원문|원서|원본|옮김|옮긴|대역|병기|다국어|중역|자막|초록|요약|목차|언어"
)
_LANGUAGE_NEGATION_RE = re.compile(
    r"확인되지\s*않|확인할\s*수\s*없|확인\s*불가|알\s*수\s*없|불명|미상|추정|보이나|보임|듯|아니|아님|않|없(?!이)"
)


def _split_clauses(text: str) -> list[str]:
    return _CLAUSE_SPLIT_RE.split(text)


def _clause_has_language_negation(clause: str) -> bool:
    """언어·번역 주장을 부정하거나 불확실하게 만드는 서술만 센다."""
    claim = _LANGUAGE_CLAIM_TOKEN_RE.search(clause)
    if claim is None:
        return False
    return any(match.start() >= claim.start() for match in _LANGUAGE_NEGATION_RE.finditer(clause))


def _has_language_negation(text: str) -> bool:
    return any(_clause_has_language_negation(clause) for clause in _split_clauses(text))


def _language_claims(text: str) -> tuple[dict[str, set[str]], bool]:
    """Read explicit language roles, never author nationality or model reasoning.

    역할을 붙일 수 없는 언어 언급이 하나라도 있으면 두 번째 값이 True다.
    주기 문장을 검사할 때 설명되지 않은 언어 주장을 걸러내는 데 쓴다.
    """
    roles: dict[str, set[str]] = {code: set() for code in _LANGUAGE_ROLES}
    unexplained = False
    for clause in _split_clauses(text):
        multilingual_spans: list[tuple[int, int]] = []
        for multilingual in _MULTILINGUAL_RE.finditer(clause):
            multilingual_spans.append(multilingual.span())
            roles["a"].update(
                _LANGUAGE_CODES.get(mention.group(), mention.group())
                for mention in _LANGUAGE_MENTION_RE.finditer(multilingual.group())
            )
        for mention in _LANGUAGE_MENTION_RE.finditer(clause):
            language = _LANGUAGE_CODES.get(mention.group(), mention.group())
            before, after = clause[:mention.start()], clause[mention.end():]
            matched = False
            for code, (prefix, suffix) in _LANGUAGE_ROLES.items():
                if re.search(prefix, before) or re.match(suffix, after):
                    roles[code].add(language)
                    matched = True
            if not matched and not any(start <= mention.start() < end for start, end in multilingual_spans):
                unexplained = True
    return roles, unexplained


def _note_claims_supported(value: str, roles: dict[str, set[str]], description_key: str) -> bool:
    """표현이 달라도 입력이 뒷받침하는 언어 관계만 말하는 주기인지 본다."""
    for bracketed in BRACKETED_TEXT_RE.findall(value):
        inner = WHITESPACE_RE.sub("", bracketed[1:-1]).casefold()
        if inner and inner not in description_key:
            return False
    if _NOTE_PARAPHRASE_RE.fullmatch(_LANGUAGE_MENTION_RE.sub("", value)) is None:
        return False
    note_roles, unexplained = _language_claims(value)
    if unexplained or not any(note_roles.values()):
        return False
    return all(languages <= roles[code] for code, languages in note_roles.items())


def _note_is_supported(
    value: str,
    *,
    roles: dict[str, set[str]],
    description_key: str,
    translation_detected: bool,
) -> bool:
    if not value.strip():
        return False
    if _has_language_negation(value):
        return False
    if value.strip() in _GENERIC_TRANSLATION_NOTES:
        return translation_detected
    if not any(keyword in value for keyword in _LANGUAGE_NOTE_KEYWORDS):
        return False
    note_key = WHITESPACE_RE.sub("", value).casefold().rstrip(".")
    if note_key and note_key in description_key:
        return True
    return _note_claims_supported(value, roles, description_key)


TRANSLATION_PHRASE_RE = re.compile(r"(?:로|으로)\s*(?:번역|옮긴|옮겨|옮김)|번역본|번역서|번역한|번역된|번역하였|번역했")


def _enforce_language_field_policy(
    fields: list["GeneratedFieldType"],
    skipped_fields: list["SkippedFieldType"],
    warnings: list[str],
    *,
    evidence: "EvidenceSchemaType | None",
) -> list["GeneratedFieldType"]:
    """Keep only source-supported language claims under a conservative policy."""
    description = evidence.description if evidence is not None and evidence.available.description else ""
    # Negative/uncertain descriptions cannot establish a positive language fact.
    description = ".".join(
        clause for clause in _split_clauses(description) if not _clause_has_language_negation(clause)
    )
    translation_detected = bool(
        evidence is not None
        and evidence.available.translation_signals
        and evidence.translation_signals.detected
    )
    roles, _ = _language_claims(description)
    # An explicit target-language translation phrase also supplies translation
    # context when the upstream hint detector has not set its flag.
    translation_context = (
        translation_detected
        or bool(roles["a"] and TRANSLATION_PHRASE_RE.search(description))
        or bool(roles["a"] and roles["h"] and roles["a"] != roles["h"])
    )
    description_key = WHITESPACE_RE.sub("", description).casefold()
    kept_fields: list["GeneratedFieldType"] = []

    for field in fields:
        if field.tag == "041":
            supported = [
                subfield for subfield in field.subfields
                if subfield.code in roles and subfield.value in roles[subfield.code]
            ]
            # 번역 정황이 확인되면 본문언어 kor은 근거가 있다. 한국어로 '옮긴' 자료의
            # 본문이 한국어라는 것은 추정이 아니다. 원저작 언어(h)는 여전히 입력이
            # 말해 줄 때만 남긴다. 이 구분이 없으면 번역서의 041이 통째로 사라진다.
            if translation_context:
                supported += [
                    subfield for subfield in field.subfields
                    if subfield.code == "a" and subfield.value == "kor" and subfield not in supported
                ]
            body_languages = {subfield.value for subfield in supported if subfield.code == "a"}
            adds_language_information = (
                len(body_languages) > 1
                or any(subfield.code != "a" for subfield in supported)
                or translation_context
            )
            if not supported or not adds_language_information:
                warnings.append("041 언어별 입력 근거 부족으로 제거됨")
                _set_skip_reason(skipped_fields, "041", FIELD_041_SKIP_REASON)
                continue
            retained = [
                subfield for subfield in field.subfields
                if subfield in supported or subfield.code in {"2", "6", "8"}
            ]
            if len(retained) != len(field.subfields):
                warnings.append("041 입력에서 확인되지 않은 언어 식별기호를 제거했습니다.")
            field.subfields = retained
            # 지시기호는 입력이 뒷받침하는 번역 정황에서만 보정한다.
            # 다국어·비번역 자료의 구분은 그대로 둔다.
            if translation_context:
                if field.indicator1 != "1":
                    field.indicator1 = "1"
                    warnings.append("041 제1지시기호를 번역물 표시(1)로 보정했습니다.")
            elif field.indicator1 == "1":
                field.indicator1 = " "
            field.review_required = True

        if field.tag == "546":
            values = [subfield.value for subfield in field.subfields if subfield.code in {"a", "b"}]
            supported_note = bool(values) and all(
                _note_is_supported(
                    value,
                    roles=roles,
                    description_key=description_key,
                    translation_detected=translation_detected,
                )
                for value in values
            )
            if not supported_note:
                warnings.append("546 언어주기 입력 근거 부족으로 제거됨")
                _set_skip_reason(skipped_fields, "546", FIELD_546_SKIP_REASON)
                continue
            field.review_required = True

        kept_fields.append(field)

    for tag in ("041", "546"):
        if any(field.tag == tag for field in kept_fields):
            _remove_skip_tag(skipped_fields, tag)
    return kept_fields


FIELD_500_SKIP_REASON = "일반주기 근거 부족: 허용 유형(원저자명·원표제·공저자·감수·한자명·수록) 아님"
# 500으로 남길 수 있는 주기 유형. 책소개 요약·장르·대상 독자는 520 범위이고,
# 수상은 586, 번역 사실은 041/546, 총서는 490이 맡는다.
GENERAL_NOTE_ALLOWED_RE = re.compile(
    r"^(?:원저자명|원저자|원표제|원서명|공저자|공역자|공그림|공편자|감수)\s*[:：]|한자명|수록|선집|\d+\s*선$"
)


def _enforce_general_note_policy(
    fields: list["GeneratedFieldType"],
    skipped_fields: list["SkippedFieldType"],
    warnings: list[str],
) -> list["GeneratedFieldType"]:
    """500은 RAG가 허용한 주기 유형만 남긴다."""

    kept_fields: list["GeneratedFieldType"] = []
    for field in fields:
        if field.tag == "500":
            values = [subfield.value.strip() for subfield in field.subfields if subfield.code == "a"]
            if not any(GENERAL_NOTE_ALLOWED_RE.search(value) for value in values):
                warnings.append("500 허용 유형이 아니어서 제거됨")
                _set_skip_reason(skipped_fields, "500", FIELD_500_SKIP_REASON)
                continue
        kept_fields.append(field)
    return kept_fields


FIELD_246_SKIP_REASON = "대체표제 근거 없음: 245 본표제와 같은 값"
FIELD_710_SKIP_REASON = "단체저자 근거 없음: 출판사는 710으로 올리지 않음"
PUBLISHER_ROLE_VALUES = frozenset({"출판", "발행", "펴냄", "출판사", "발행처"})
TITLE_KEY_RE = re.compile(r"[^0-9A-Za-z가-힣]+")


def _title_key(value: str) -> str:
    return TITLE_KEY_RE.sub("", value).casefold()


def _enforce_added_entry_policy(
    fields: list["GeneratedFieldType"],
    skipped_fields: list["SkippedFieldType"],
    warnings: list[str],
    *,
    biblio: "BiblioSchemaType | None",
) -> list["GeneratedFieldType"]:
    """246/710을 RAG skip 규칙대로 거른다.

    - 246: 245 본표제와 구두점·공백만 다른 값은 다른 표제가 아니다.
    - 710: 출판사·발행처는 단체저자가 아니다. 역할어가 출판이거나 이름이
      biblio.publisher와 겹치면 제거한다.
    """

    title_keys: set[str] = set()
    publisher_key = ""
    if biblio is not None:
        title_keys = {_title_key(biblio.title), _title_key(biblio.title.split(":", 1)[0])}
        title_keys.discard("")
        publisher_key = _title_key(biblio.publisher)

    kept_fields: list["GeneratedFieldType"] = []
    for field in fields:
        if field.tag == "246" and title_keys:
            values = [subfield.value for subfield in field.subfields if subfield.code == "a"]
            if values and all(_title_key(value) in title_keys for value in values):
                warnings.append("246이 245 본표제와 같아 제거됨")
                _set_skip_reason(skipped_fields, "246", FIELD_246_SKIP_REASON)
                continue

        if field.tag == "710":
            roles = {subfield.value.strip() for subfield in field.subfields if subfield.code == "e"}
            names = [_title_key(subfield.value) for subfield in field.subfields if subfield.code == "a"]
            publisher_like = bool(publisher_key) and any(
                name and (name in publisher_key or publisher_key in name) for name in names
            )
            if roles & PUBLISHER_ROLE_VALUES or publisher_like:
                warnings.append("710에 출판사가 들어가 제거됨")
                _set_skip_reason(skipped_fields, "710", FIELD_710_SKIP_REASON)
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
    _assign_generated_by(parsed)
    _preprocess_policy_violations(parsed)
    try:
        result = GenerateResult.model_validate(parsed)
    except ValidationError as exc:
        logger.warning("LLM 출력 스키마 검증 실패: %s", exc)
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
    fields = _enforce_language_field_policy(fields, skipped_fields, warnings, evidence=evidence)
    fields = _enforce_added_entry_policy(fields, skipped_fields, warnings, biblio=biblio)
    fields = _enforce_general_note_policy(fields, skipped_fields, warnings)
    fields = _remove_redundant_653_fields(fields, skipped_fields, biblio=biblio, evidence=evidence)

    return GenerateResult(fields=fields, skipped_fields=skipped_fields, warnings=warnings)
