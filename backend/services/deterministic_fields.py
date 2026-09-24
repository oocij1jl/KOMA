"""API 값에서 규칙으로 직접 만드는 MARC 필드.

이 모듈은 LLM을 호출하지 않는다. `biblio`에 이미 있는 값을 KORMARC 규칙대로
식별기호에 배치할 뿐이며, 값 자체를 새로 만들거나 고치지 않는다.

여기서 만든 필드는 LLM 생성 대상에서 제외되므로 같은 태그가 두 경로로
중복 생성되지 않는다.

규칙 출처는 `ai/rag/docs/kormarc/fields/`의 각 필드 문서다.
"""

from __future__ import annotations

import importlib
import re
from typing import TYPE_CHECKING, cast

try:  # pragma: no cover - import path depends on startup context
    from backend.schemas import llm_output as llm_output_schema
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    llm_output_schema = importlib.import_module("schemas.llm_output")

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.llm_output import GeneratedField as GeneratedFieldType
    from backend.schemas.llm_output import SkippedField as SkippedFieldType
    from backend.schemas.lookup import BiblioSchema as BiblioSchemaType

GeneratedField = cast(type["GeneratedFieldType"], llm_output_schema.GeneratedField)
SkippedField = cast(type["SkippedFieldType"], llm_output_schema.SkippedField)


# 이 모듈이 담당하는 태그. marc_generator가 LLM 생성 대상에서 뺀다.
DETERMINISTIC_TAGS: tuple[str, ...] = ("245",)

# 책임표시 구분에 쓰는 역할어. 긴 표현을 먼저 찾는다.
RESPONSIBILITY_ROLE_WORDS: tuple[str, ...] = (
    "엮고 옮김",
    "글·그림",
    "글 그림",
    "글그림",
    "지음",
    "옮김",
    "엮음",
    "편역",
    "편저",
    "번역",
    "감수",
    "사진",
    "그림",
    "글",
    "저",
    "역",
    "편",
)
# 역할어가 앞에 붙는 표현(예: "지은이 박아림")은 책임표시를 나누는 기준이 아니다.
RESPONSIBILITY_PREFIX_WORDS: tuple[str, ...] = (
    "지은이",
    "옮긴이",
    "그린이",
    "엮은이",
    "글쓴이",
    "사진가",
)
_ROLE_ALTERNATION = "|".join(re.escape(word) for word in RESPONSIBILITY_ROLE_WORDS)
# 역할어 뒤가 문자열 끝이거나 공백일 때만 경계로 본다. 이름 일부를 자르지 않기 위함이다.
RESPONSIBILITY_BOUNDARY_RE = re.compile(rf"(?:{_ROLE_ALTERNATION})(?=\s|$)")

PARALLEL_TITLE_SEPARATOR_RE = re.compile(r"\s*=\s*")
SUBTITLE_SEPARATOR_RE = re.compile(r"\s*:\s*")
WHITESPACE_RE = re.compile(r"\s+")


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", str(value)).strip()


def split_parallel_title(title: str) -> tuple[str, str]:
    """' = ' 구분자가 있을 때만 본표제와 대등표제로 나눈다."""

    parts = PARALLEL_TITLE_SEPARATOR_RE.split(title, maxsplit=1)
    if len(parts) != 2:
        return title, ""

    main, parallel = _clean(parts[0]), _clean(parts[1])
    if not main or not parallel:
        return title, ""
    return main, parallel


def split_subtitle(title: str) -> tuple[str, str]:
    """':' 구분자가 있고 앞뒤가 모두 있을 때만 본표제와 부제로 나눈다.

    구분자가 없으면 나누지 않는다. 근거 없는 부제를 만들지 않기 위한 규칙이다.
    """

    parts = SUBTITLE_SEPARATOR_RE.split(title, maxsplit=1)
    if len(parts) != 2:
        return title, ""

    main, subtitle = _clean(parts[0]), _clean(parts[1])
    if not main or not subtitle:
        return title, ""
    return main, subtitle


def _has_name_before_role(segment: str) -> bool:
    """역할어 앞에 이름 성분이 있는지 본다.

    "이규희 글"은 나눌 수 있지만 "글 유상아"의 선행 역할어는 기준이 아니다.
    """

    stripped = _clean(segment)
    if not stripped:
        return False
    for prefix in RESPONSIBILITY_PREFIX_WORDS:
        if stripped.startswith(prefix):
            stripped = _clean(stripped[len(prefix) :])
            break
    return bool(stripped)


def split_responsibility(author: str) -> list[str]:
    """`biblio.author`를 책임표시 단위로 나눈다.

    1. `;`가 있으면 그 기준으로 나눈다.
    2. 없으면 역할어 뒤에서 나눈다. 역할어 앞에 이름이 없으면 나누지 않는다.
    3. 둘 다 없으면 통째로 하나의 책임표시로 둔다. 공백만 보고 인명을 쪼개지 않는다.
    """

    cleaned = _clean(author)
    if not cleaned:
        return []

    if ";" in cleaned:
        return [segment for segment in (_clean(part) for part in cleaned.split(";")) if segment]

    statements: list[str] = []
    start = 0
    for match in RESPONSIBILITY_BOUNDARY_RE.finditer(cleaned):
        segment = cleaned[start : match.end()]
        before_role = cleaned[start : match.start()]
        if not _has_name_before_role(before_role):
            continue
        statements.append(_clean(segment))
        start = match.end()

    tail = _clean(cleaned[start:])
    if tail:
        statements.append(tail)

    return statements or [cleaned]


def build_245(biblio: "BiblioSchemaType") -> tuple["GeneratedFieldType | None", "SkippedFieldType | None"]:
    """biblio.title/volume/author로 245를 만든다.

    표제가 없으면 생성하지 않는다. 값은 전사만 하고 교정하지 않는다.
    """

    title = _clean(getattr(biblio, "title", ""))
    if not title:
        return None, SkippedField(tag="245", reason="표제 근거 없음: 245 생성 불가")

    main_title, parallel_title = split_parallel_title(title)
    main_title, subtitle = split_subtitle(main_title)
    volume = _clean(getattr(biblio, "volume", ""))
    statements = split_responsibility(_clean(getattr(biblio, "author", "")))

    subfields: list[dict[str, str]] = [{"code": "a", "value": main_title}]
    if parallel_title:
        subfields.append({"code": "x", "value": parallel_title})
    if subtitle:
        subfields.append({"code": "b", "value": subtitle})
    if volume:
        subfields.append({"code": "n", "value": volume})
    for index, statement in enumerate(statements):
        subfields.append({"code": "d" if index == 0 else "e", "value": statement})

    # 제1지시기호: 이 서비스는 1XX 기본표목을 만들지 않으므로 항상 0이다.
    # 제2지시기호: 본표제가 원괄호 관제로 시작할 때만 1이다.
    indicator2 = "1" if main_title.startswith("(") and ")" in main_title else "0"

    notes: list[str] = ["biblio.title/author 전사"]
    if subtitle:
        notes.append("표제 구분자 기준 부제 분리 — 검수 필요")
    if len(statements) > 1:
        notes.append("역할어 기준 책임표시 분리 — 검수 필요")
    if not statements:
        notes.append("책임표시 근거 없음 — 저자 확인 필요")

    field = GeneratedField(
        tag="245",
        source="api",
        generated_by="rule",
        indicator1="0",
        indicator2=indicator2,
        subfields=[llm_output_schema.SubfieldItem(**subfield) for subfield in subfields],
        review_required=True,
        confidence="high" if statements else "medium",
        evidence=None,
        note=". ".join(notes),
    )
    return field, None


def build_deterministic_fields(
    biblio: "BiblioSchemaType",
) -> tuple[list["GeneratedFieldType"], list["SkippedFieldType"]]:
    """규칙으로 만들 수 있는 필드를 모두 만든다."""

    fields: list[GeneratedFieldType] = []
    skipped: list[SkippedFieldType] = []

    field_245, skipped_245 = build_245(biblio)
    if field_245 is not None:
        fields.append(field_245)
    if skipped_245 is not None:
        skipped.append(skipped_245)

    return fields, skipped
