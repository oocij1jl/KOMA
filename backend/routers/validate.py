"""
/api/validate  ─  MARC 형식 1차 검증 라우터

검증 항목
  - 태그 3자리 숫자 여부
  - 지시기호 2자리 (각 1자리) 여부
  - 필수 식별기호 존재 여부
  - ISBN 형식 (020 필드)
  - 필수 필드 누락 (020, 245, 260)
"""

import re
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------

class Subfield(BaseModel):
    code: str       # 단일 소문자 알파벳 또는 숫자
    value: str


class MarcField(BaseModel):
    tag: str        # 3자리 숫자 문자열
    ind1: str = " "  # 1자리 (공백 포함)
    ind2: str = " "
    subfields: list[Subfield] = []


class ValidateRequest(BaseModel):
    fields: list[MarcField]


# ---------------------------------------------------------------------------
# 검증 규칙
# ---------------------------------------------------------------------------

REQUIRED_TAGS = {"020", "245", "260"}

REQUIRED_SUBFIELDS: dict[str, list[str]] = {
    "020": ["a"],   # ISBN
    "245": ["a"],   # 본표제
    "260": ["b", "c"],  # 발행처, 발행연도
}

ISBN_RE = re.compile(r"^(\d{9}[\dX]|\d{13})")

def validate_marc_fields(fields: list[MarcField]) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    present_tags = {f.tag for f in fields}

    for field in fields:
        tag = field.tag
        loc = f"[{tag}]"

        # 태그 3자리 숫자 검증
        if not re.match(r"^\d{3}$", tag):
            errors.append({"field": tag, "message": f"{loc} 태그는 3자리 숫자여야 합니다."})
            continue  # 이하 검증 skip

        # 지시기호 검증 (각 1자리, 공백 포함)
        if len(field.ind1) != 1:
            errors.append({"field": tag, "message": f"{loc} ind1은 정확히 1자리여야 합니다."})
        if len(field.ind2) != 1:
            errors.append({"field": tag, "message": f"{loc} ind2은 정확히 1자리여야 합니다."})

        # 식별기호 코드 검증 (단일 문자)
        for sf in field.subfields:
            if not re.match(r"^[a-z0-9]$", sf.code):
                errors.append({
                    "field": tag,
                    "message": f"{loc} $${sf.code}: 식별기호는 소문자 알파벳 또는 숫자 1자리여야 합니다."
                })

        # 필수 식별기호 존재 여부
        if tag in REQUIRED_SUBFIELDS:
            present_codes = {sf.code for sf in field.subfields}
            for required_code in REQUIRED_SUBFIELDS[tag]:
                if required_code not in present_codes:
                    errors.append({
                        "field": tag,
                        "message": f"{loc} 필수 식별기호 $${required_code}가 없습니다."
                    })

        # 020: ISBN 형식 검증
        if tag == "020":
            for sf in field.subfields:
                if sf.code == "a":
                    raw_isbn = sf.value.split()[0].replace("-", "")  # 수식어 이전 값
                    if not ISBN_RE.match(raw_isbn):
                        errors.append({
                            "field": "020",
                            "message": f"[020] $$a ISBN 형식이 유효하지 않습니다: {sf.value!r}"
                        })

    # 필수 필드 누락
    for tag in REQUIRED_TAGS:
        if tag not in present_tags:
            errors.append({"field": tag, "message": f"필수 필드 {tag}가 누락되었습니다."})

    # 060/082/650 미검수 경고
    for field in fields:
        if field.tag in {"056", "082", "650"}:
            warnings.append({
                "field": field.tag,
                "message": f"[{field.tag}] AI 생성 필드입니다. 사서 검수가 필요합니다."
            })

    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------

@router.post("/validate")
async def validate_marc(body: ValidateRequest):
    """
    MARC 필드 배열에 대한 1차 형식 검증 수행.

    - 에러: 수정 필요 (태그 형식, 필수 필드 누락, ISBN 오류 등)
    - 경고: 검수 권장 (AI 생성 분류기호, 주제명 등)
    """
    result = validate_marc_fields(body.fields)
    return result