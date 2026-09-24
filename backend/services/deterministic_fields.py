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
# 값이 없으면 LLM에 넘기지 않고 skip 사유를 남긴다. 추론으로 채울 필드가 아니다.
DETERMINISTIC_TAGS: tuple[str, ...] = ("020", "245", "250", "260", "300", "490", "056", "082")

# 300 ▼a 수량 단위. API 문자열에 이 단위가 있으면 그대로 따른다.
KOREAN_EXTENT_UNITS: tuple[str, ...] = ("장", "책", "권", "면", "매")
NUMBER_RE = re.compile(r"\d+")
# book_size에서 숫자·구분자를 제거하고 남는 게 있으면 "알 수 없는 단위"로 본다.
SIZE_UNIT_STRIP_RE = re.compile(r"[\d*x×\s.,]+")

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


def _extract_extent(page: str) -> str:
    """`biblio.page`에서 수량과 특정자료종별을 만든다.

    숫자가 없으면 빈 문자열을 돌려준다. 수량을 추정하지 않는다.
    """

    cleaned = _clean(page)
    if not cleaned:
        return ""

    match = NUMBER_RE.search(cleaned)
    if match is None:
        return ""

    count = match.group()
    # API가 이미 단위를 갖고 있으면 그 단위를 따른다. 없으면 도서 기본 단위 p.를 쓴다.
    for unit in KOREAN_EXTENT_UNITS:
        if unit in cleaned:
            return f"{count}{unit}"
    return f"{count} p."


def _extract_height_cm(book_size: str) -> str:
    """`biblio.book_size`에서 세로 크기(cm)를 만든다.

    - `22 cm` 처럼 cm 단위면 그대로 쓴다.
    - `128*188mm` 처럼 두 값이면 큰 값을 세로로 보고 cm로 올림한다.
    - `188*257`처럼 단위 표기가 아예 없는 경우: 정보나루/국중도 API가 실제로
      이 형태(가로*세로, mm, 단위 생략)로 값을 준다(2026-09-25 실API 응답
      `book_size='188*257'` 확인). 숫자 외 다른 문자가 전혀 없고 최댓값이
      100 이상일 때만 mm 관례를 적용한다 — "22"처럼 이미 cm로 보이는 작은
      값이나 알 수 없는 단위 문자가 섞인 값은 여전히 추정하지 않는다.
    - 그 외에는 빈 문자열을 돌려준다. 임의 환산하지 않는다.
    """

    cleaned = _clean(book_size).lower()
    if not cleaned:
        return ""

    numbers = [int(value) for value in NUMBER_RE.findall(cleaned)]
    if not numbers:
        return ""

    if "cm" in cleaned:
        return f"{max(numbers)} cm"
    if "mm" in cleaned:
        millimeters = max(numbers)
        return f"{-(-millimeters // 10)} cm"

    residual = SIZE_UNIT_STRIP_RE.sub("", cleaned)
    if not residual and max(numbers) >= 100:
        millimeters = max(numbers)
        return f"{-(-millimeters // 10)} cm"

    # 단위 표기가 없고 위 관례도 적용할 수 없으면 값의 크기로 추정하지 않는다.
    return ""


def build_300(biblio: "BiblioSchemaType") -> tuple["GeneratedFieldType | None", "SkippedFieldType | None"]:
    """biblio.page/book_size로 300을 만든다.

    삽화(▼b)는 근거가 없으므로 만들지 않는다. 지시기호는 미정의라 공백이다.
    """

    extent = _extract_extent(_clean(getattr(biblio, "page", "")))
    height = _extract_height_cm(_clean(getattr(biblio, "book_size", "")))

    subfields: list[dict[str, str]] = []
    if extent:
        subfields.append({"code": "a", "value": extent})
    if height:
        subfields.append({"code": "c", "value": height})

    if not subfields:
        return None, SkippedField(tag="300", reason="형태사항 근거 없음: page/book_size 미수집")

    notes = ["biblio.page/book_size 변환"]
    if not extent:
        notes.append("수량 근거 없음")
    if not height:
        notes.append("크기 근거 없음 또는 단위 미확인")

    field = GeneratedField(
        tag="300",
        source="api",
        generated_by="rule",
        indicator1=" ",
        indicator2=" ",
        subfields=[llm_output_schema.SubfieldItem(**subfield) for subfield in subfields],
        review_required=True,
        confidence="medium",
        evidence=None,
        note=". ".join(notes),
    )
    return field, None


def _build_classification(
    *,
    tag: str,
    value: str,
    edition: str,
    skip_reason: str,
) -> tuple["GeneratedFieldType | None", "SkippedFieldType | None"]:
    """056/082 공통. API 분류기호가 있을 때만 전사한다."""

    number = _clean(value)
    if not number:
        return None, SkippedField(tag=tag, reason=skip_reason)

    subfields: list[dict[str, str]] = [{"code": "a", "value": number}]
    notes = [f"API 분류기호 전사({tag})"]

    edition_value = _clean(edition)
    if edition_value:
        subfields.append({"code": "2", "value": edition_value})
    else:
        notes.append("판차 미수집 — 검수 필요")

    # 056은 지시기호가 미정의라 공백이다.
    # 082는 판 유형(제1)과 부여 출처(제2)를 확정할 근거가 없으므로 공백으로 두고 검수에 맡긴다.
    field = GeneratedField(
        tag=tag,
        source="api",
        generated_by="rule",
        indicator1=" ",
        indicator2=" ",
        subfields=[llm_output_schema.SubfieldItem(**subfield) for subfield in subfields],
        review_required=True,
        confidence="medium",
        evidence=None,
        note=". ".join(notes),
    )
    return field, None


def build_056(biblio: "BiblioSchemaType") -> tuple["GeneratedFieldType | None", "SkippedFieldType | None"]:
    return _build_classification(
        tag="056",
        value=getattr(biblio, "kdc", ""),
        edition=getattr(biblio, "kdc_edition", ""),
        skip_reason="KDC 근거 없음: API 분류기호 미수집",
    )


def build_082(biblio: "BiblioSchemaType") -> tuple["GeneratedFieldType | None", "SkippedFieldType | None"]:
    return _build_classification(
        tag="082",
        value=getattr(biblio, "ddc", ""),
        edition=getattr(biblio, "ddc_edition", ""),
        skip_reason="DDC 근거 없음: API 분류기호 미수집",
    )


def build_020(biblio: "BiblioSchemaType") -> tuple[list["GeneratedFieldType"], list["SkippedFieldType"]]:
    """biblio의 ISBN·부가기호·가격·세트 정보로 020을 만든다.

    낱권 번호와 세트 번호는 제1지시기호가 다르므로 필드를 나눠 기술한다.
    """

    fields: list[GeneratedFieldType] = []

    isbn = _clean(getattr(biblio, "isbn_ea", ""))
    add_code = _clean(getattr(biblio, "isbn_add_code", ""))
    price = _clean(getattr(biblio, "price", ""))
    if isbn or price:
        subfields: list[dict[str, str]] = []
        if isbn:
            subfields.append({"code": "a", "value": isbn})
        # 부가기호는 우리나라 ISBN에만 쓰는 5자리 숫자다. 형식이 다르면 버린다.
        if add_code.isdigit() and len(add_code) == 5:
            subfields.append({"code": "g", "value": add_code})
        if price:
            subfields.append({"code": "c", "value": price})
        fields.append(
            GeneratedField(
                tag="020",
                source="api",
                generated_by="rule",
                indicator1=" ",
                indicator2=" ",
                subfields=[llm_output_schema.SubfieldItem(**subfield) for subfield in subfields],
                review_required=False,
                confidence="high",
                evidence=None,
                note="biblio ISBN 전사",
            )
        )

    set_isbn = _clean(getattr(biblio, "set_isbn", ""))
    if set_isbn:
        set_subfields: list[dict[str, str]] = [{"code": "a", "value": set_isbn}]
        set_expression = _clean(getattr(biblio, "set_expression", ""))
        if set_expression:
            set_subfields.append({"code": "q", "value": set_expression})
        set_add_code = _clean(getattr(biblio, "set_add_code", ""))
        if set_add_code.isdigit() and len(set_add_code) == 5:
            set_subfields.append({"code": "g", "value": set_add_code})
        fields.append(
            GeneratedField(
                tag="020",
                source="api",
                generated_by="rule",
                indicator1="1",
                indicator2=" ",
                subfields=[llm_output_schema.SubfieldItem(**subfield) for subfield in set_subfields],
                review_required=True,
                confidence="high",
                evidence=None,
                note="세트 ISBN 전사",
            )
        )

    if not fields:
        return [], [SkippedField(tag="020", reason="ISBN 근거 없음: 020 생성 불가")]
    return fields, []


def build_250(biblio: "BiblioSchemaType") -> tuple["GeneratedFieldType | None", "SkippedFieldType | None"]:
    """판사항은 API에 명시된 문구가 있을 때만 만든다. 초판을 가정하지 않는다."""

    edition_stmt = _clean(getattr(biblio, "edition_stmt", ""))
    if not edition_stmt:
        return None, SkippedField(tag="250", reason="판사항 근거 없음: 판 표시 미수집")

    field = GeneratedField(
        tag="250",
        source="api",
        generated_by="rule",
        indicator1=" ",
        indicator2=" ",
        subfields=[llm_output_schema.SubfieldItem(code="a", value=edition_stmt)],
        review_required=False,
        confidence="high",
        evidence=None,
        note="biblio.edition_stmt 전사",
    )
    return field, None


def build_260(biblio: "BiblioSchemaType") -> tuple["GeneratedFieldType | None", "SkippedFieldType | None"]:
    """발행사항을 만든다.

    발행지(▼a)는 두 API 모두 제공하지 않으므로 생성하지 않는다. 출판사 주소를
    추정해 넣지 않는다.
    """

    publisher = _clean(getattr(biblio, "publisher", ""))
    year = _clean(getattr(biblio, "publish_year", ""))

    subfields: list[dict[str, str]] = []
    if publisher:
        subfields.append({"code": "b", "value": publisher})
    if year:
        subfields.append({"code": "c", "value": year})

    if not subfields:
        return None, SkippedField(tag="260", reason="발행사항 근거 없음: 발행처·발행년 미수집")

    notes = ["biblio.publisher/publish_year 전사", "발행지 미수집 — 검수 필요"]
    field = GeneratedField(
        tag="260",
        source="api",
        generated_by="rule",
        indicator1=" ",
        indicator2=" ",
        subfields=[llm_output_schema.SubfieldItem(**subfield) for subfield in subfields],
        review_required=True,
        confidence="high",
        evidence=None,
        note=". ".join(notes),
    )
    return field, None


def build_490(biblio: "BiblioSchemaType") -> tuple["GeneratedFieldType | None", "SkippedFieldType | None"]:
    """총서사항을 만든다.

    제1지시기호는 총서 부출 여부다. 이 서비스는 830 총서부출표목을 만들지
    않으므로 `0`(총서를 부출하지 않음)으로 둔다.
    """

    series_title = _clean(getattr(biblio, "series_title", ""))
    if not series_title:
        return None, SkippedField(tag="490", reason="총서사항 근거 없음: 총서명 미수집")

    subfields: list[dict[str, str]] = [{"code": "a", "value": series_title}]
    series_no = _clean(getattr(biblio, "series_no", ""))
    if series_no:
        subfields.append({"code": "v", "value": series_no})

    indicator2 = "1" if series_title.startswith("(") and ")" in series_title else "0"
    field = GeneratedField(
        tag="490",
        source="api",
        generated_by="rule",
        indicator1="0",
        indicator2=indicator2,
        subfields=[llm_output_schema.SubfieldItem(**subfield) for subfield in subfields],
        review_required=True,
        confidence="high",
        evidence=None,
        note="biblio.series_title 전사. 총서 부출(830)은 전거 확인 전까지 생성하지 않음",
    )
    return field, None


def _as_lists(
    result: tuple["GeneratedFieldType | None", "SkippedFieldType | None"],
) -> tuple[list["GeneratedFieldType"], list["SkippedFieldType"]]:
    field, skipped = result
    return ([field] if field is not None else []), ([skipped] if skipped is not None else [])


BUILDERS = {
    "020": build_020,
    "245": lambda biblio: _as_lists(build_245(biblio)),
    "250": lambda biblio: _as_lists(build_250(biblio)),
    "260": lambda biblio: _as_lists(build_260(biblio)),
    "300": lambda biblio: _as_lists(build_300(biblio)),
    "490": lambda biblio: _as_lists(build_490(biblio)),
    "056": lambda biblio: _as_lists(build_056(biblio)),
    "082": lambda biblio: _as_lists(build_082(biblio)),
}


def build_deterministic_fields(
    biblio: "BiblioSchemaType",
) -> tuple[list["GeneratedFieldType"], list["SkippedFieldType"]]:
    """규칙으로 만들 수 있는 필드를 모두 만든다.

    값이 없으면 필드 대신 skip 사유를 남긴다. 추론으로 채우지 않는다.
    """

    fields: list["GeneratedFieldType"] = []
    skipped: list["SkippedFieldType"] = []

    for tag in DETERMINISTIC_TAGS:
        built_fields, built_skips = BUILDERS[tag](biblio)
        fields.extend(built_fields)
        skipped.extend(built_skips)

    return fields, skipped
