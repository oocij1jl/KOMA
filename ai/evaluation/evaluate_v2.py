"""RAG 규칙 기반 평가 v2.

v1(evaluate_koma.py)은 gold 값과 문자열이 맞는지, 그리고 생성했는지만 본다.
보강된 RAG 규칙은 "근거가 없으면 만들지 않는다"가 핵심이라, v1의 생성률·정확도만
보면 올바른 보류가 감점되고 근거 없는 과잉 생성은 드러나지 않는다.
v2는 결과를 세 축으로 나눠 채점하고 종합한다.

A. 값 정확도    gold가 있는 (도서, 필드)만 분모로 쓴다. 생성하지 않았으면 0점.
                부분 점수 평균과 exact 비율을 함께 낸다. 700 인명을 새로 채점한다.
B. 규칙 준수율  ai/rag/chunks의 generation/forbidden 규칙을 코드 검사로 옮겼다.
                gold가 필요 없다. (도서, 규칙) 단위로 해당 여부와 통과 여부를 센다.
C. 생성 판단    태그별로 "만들 것인가/보류할 것인가"가 gold와 맞는지 본다.
                gold에 없고 생성도 안 한 경우를 올바른 보류(정답)로 센다.
KOMA-Q          A·B·C의 단순 평균.

v1은 기준선 재현을 위해 수정하지 않는다. v2는 v1의 파서와 비교 함수를 재사용한다.
여러 결과 디렉터리를 같은 기준으로 채점해 나란히 비교한다.

사용 예

    python3 ai/evaluation/evaluate_v2.py \
        --run mid-presentation=mid_result/eval_results \
        --run after-rag=ai/evaluation/runs/after-rag/results \
        --out-dir ai/evaluation/runs/v2-compare
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_koma as v1  # noqa: E402


EVALUATOR_VERSION = "v2.1"  # 2026-09-26 기준 승인·동결. 채점 규칙을 바꾸면 버전을 올린다.

# A축 채점 필드. 250/082는 gold가 생기면 자동으로 들어오도록 v1 필드도 포함한다.
VALUE_FIELDS = ("020", "245", "250", "260", "300", "041", "056", "082", "653", "700")

# C축 판단 대상. 서비스가 생성하거나 명시적으로 보류하는 태그만 넣는다.
# 650·830·950은 정책상 기본 제외라 B축(POLICY_EXCLUDED_TAGS)에서 본다.
DECISION_TAGS = ("020", "041", "056", "082", "245", "246", "250", "260", "300", "490", "500", "546", "653", "700", "710")

# gold 쪽 대응 태그. 기관 레코드는 총서를 폐지된 440으로 기술했고, 주제어는
# 650과 653을 함께 쓴다(v1과 같은 기준).
GOLD_TAG_ALIASES = {"490": ("490", "440"), "653": ("650", "653")}

# 정책상 자동 생성하지 않는 태그: 650 표목표 대조 전 보류, 830 전거 필요, 950 기관 로컬.
POLICY_EXCLUDED_TAGS = ("650", "830", "950")

# 책임표시·인명에서 걷어낼 역할어. v1은 부분 문자열로 지워 "엮고 옮긴이"에서
# "엮고", "저자"에서 "자"가 인명으로 남았다. v2는 토큰 단위로 비교한다.
ROLE_TOKENS = frozenset(
    {
        "지은이", "옮긴이", "그린이", "엮은이", "글쓴이", "지음", "옮김", "엮음", "엮고",
        "편역", "편저", "편집", "편자", "공편", "번역", "역자", "역주", "감수", "감수자",
        "사진", "공저", "공역", "그림", "그림작가", "글", "글그림", "저", "저자", "대표저자",
        "역", "편", "씀", "삽화", "삽화가", "일러스트", "기획", "원작", "각색", "구성",
        "해설", "수록", "작가", "외", "공", "作", "著", "譯", "編",
    }
)
HANGUL_RE = re.compile(r"[가-힣]")

KDC_DDC_RE = re.compile(r"^\d{3}(?:\.\d+)?$")
LANG_CODE_RE = re.compile(r"^[a-z]{3}$")
ISBN_ADD_CODE_RE = re.compile(r"^\d{5}$")
PAGE_UNIT_RE = re.compile(r"(?:p\.?|장|책|권|면|매)\s*$")
MEANINGLESS_PAGE_RE = re.compile(r"^\D*0+\s*(?:p\.?)?\s*$")
SIZE_UNIT_RE = re.compile(r"\d\s*cm$")
MULTI_NAME_RE = re.compile(r"[·/;]")
GENERIC_546_RE = re.compile(r"^한국어(?:로)?\s*(?:된|기술된|쓰인|작성된)?\s*\S*$")
NEGATED_NOTE_RE = re.compile(r"확인되지\s*않|확인할\s*수\s*없|정황은\s*없|근거\s*(?:가\s*)?(?:부족|없)|보이나|아님|없음")
TRANSLATION_NOTE_RE = re.compile(r"번역|원작|원저")
TRANSLATION_ONLY_500_RE = re.compile(r"^(?:한국어\s*)?번역(?:서|본|물|\s*자료)?$")
PUBLISHER_ROLE_VALUES = frozenset({"출판", "발행", "펴냄", "출판사", "발행처"})


# ---------------------------------------------------------------------------
# 공통 도우미
# ---------------------------------------------------------------------------


def raw_fields(payload: dict[str, Any], tag: str) -> list[dict[str, Any]]:
    return [field for field in payload.get("fields", []) if isinstance(field, dict) and field.get("tag") == tag]


def raw_values(field: dict[str, Any], code: str) -> list[str]:
    return [
        str(subfield.get("value", ""))
        for subfield in field.get("subfields", [])
        if isinstance(subfield, dict) and subfield.get("code") == code and str(subfield.get("value", "")).strip()
    ]


def raw_codes(field: dict[str, Any]) -> list[str]:
    return [str(subfield.get("code", "")) for subfield in field.get("subfields", []) if isinstance(subfield, dict)]


def compact_key(value: str) -> str:
    """구두점·공백·대소문자를 무시한 비교 키."""

    return v1.TITLE_COMPARE_RE.sub("", value).casefold()


def name_tokens(value: str) -> list[str]:
    cleaned = v1.BRACKET_TEXT_RE.sub(" ", value)
    tokens = []
    for token in v1.NAME_SPLIT_RE.split(cleaned):
        token = token.strip().casefold()
        if token and token not in ROLE_TOKENS and not token.isdigit():
            tokens.append(token)
    return tokens


def string_component(gold: str, koma: str) -> float:
    if gold and koma and gold == koma:
        return 1.0
    if gold and koma and (gold in koma or koma in gold):
        return 0.5
    return 0.0


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def gold_has_tag(gold: v1.RecordData, tag: str) -> bool:
    for alias in GOLD_TAG_ALIASES.get(tag, (tag,)):
        for occurrence in gold.tags.get(alias, []):
            if any(value.strip() for _, value in occurrence.subfields):
                return True
    return False


# ---------------------------------------------------------------------------
# A. 값 정확도
# ---------------------------------------------------------------------------


def responsibility_names(occurrence: v1.FieldOccurrence) -> set[str]:
    names: set[str] = set()
    for code, value in occurrence.subfields:
        if code in ("d", "e"):
            names.update(name_tokens(value))
    return names


def score_245_occurrence(gold: v1.FieldOccurrence, koma: v1.FieldOccurrence) -> dict[str, Any]:
    components: dict[str, float] = {}
    gold_title = v1.subfield_value(gold, "a")
    koma_title = v1.subfield_value(koma, "a")
    if gold_title or koma_title:
        components["title"] = string_component(gold_title, koma_title)

    gold_subtitle = v1.subfield_value(gold, "b")
    if gold_subtitle:
        components["subtitle"] = string_component(gold_subtitle, v1.subfield_value(koma, "b"))

    gold_names = responsibility_names(gold)
    koma_names = responsibility_names(koma)
    if gold_names:
        components["responsibility"] = v1.name_set_score(gold_names, koma_names)

    score = round(sum(components.values()) / len(components), 4) if components else 0.0
    return {"score": score, "components": components, "gold_names": sorted(gold_names), "koma_names": sorted(koma_names)}


def score_245(gold: v1.RecordData, payload: dict[str, Any]) -> dict[str, Any] | None:
    gold_fields = v1.extract_structured_occurrences(v1.normalize_field_map(gold.tags), "245")
    koma_map, _ = v1.normalize_koma_result(payload)
    koma_fields = v1.extract_structured_occurrences(koma_map, "245")
    if not gold_fields:
        return None
    if not koma_fields:
        return {"score": 0.0, "components": {}, "gold_names": [], "koma_names": []}
    return max(
        (score_245_occurrence(gold_field, koma_field) for gold_field in gold_fields for koma_field in koma_fields),
        key=lambda item: item["score"],
    )


def person_keys(value: str) -> set[str]:
    """한 사람 이름의 비교 키 집합. '카프카, 프란츠'와 '프란츠 카프카'를 같게 본다."""

    tokens = name_tokens(value)
    if not tokens or len(tokens) > 4:
        return {"".join(tokens)} if tokens else set()
    return {"".join(order) for order in permutations(tokens)}


def is_attainable_person(value: str) -> bool:
    """원어명(로마자·한자) 부출은 API 저자 문자열로 얻을 수 없어 채점에서 뺀다."""

    return bool(HANGUL_RE.search(value))


def score_700(gold: v1.RecordData, payload: dict[str, Any]) -> dict[str, Any] | None:
    gold_people = [
        value
        for occurrence in gold.tags.get("700", [])
        for code, value in occurrence.subfields
        if code == "a" and value.strip() and is_attainable_person(value)
    ]
    if not gold_people:
        return None

    koma_people = [value for field in raw_fields(payload, "700") for value in raw_values(field, "a")]
    if not koma_people:
        return {"score": 0.0, "precision": 0.0, "recall": 0.0, "matched": [], "gold_only": gold_people, "koma_only": []}

    remaining = list(gold_people)
    matched: list[tuple[str, str]] = []
    koma_only: list[str] = []
    for koma_value in koma_people:
        koma_keys = person_keys(koma_value)
        hit = next((gold_value for gold_value in remaining if person_keys(gold_value) & koma_keys), None)
        if hit is None:
            koma_only.append(koma_value)
            continue
        matched.append((koma_value, hit))
        remaining.remove(hit)

    precision = len(matched) / len(koma_people)
    recall = len(matched) / len(gold_people)
    f1 = 0.0 if not matched else 2 * precision * recall / (precision + recall)
    return {
        "score": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "matched": matched,
        "gold_only": remaining,
        "koma_only": koma_only,
    }


def value_scores(gold: v1.RecordData, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """(필드 -> {score, detail}). gold가 없는 필드는 넣지 않는다."""

    v1_result = v1.compare_record(gold, payload, allow_partial_653=True)["field_results"]
    scores: dict[str, dict[str, Any]] = {}
    for tag in VALUE_FIELDS:
        if tag == "245":
            detail = score_245(gold, payload)
            if detail is not None:
                scores[tag] = {"score": detail["score"], "detail": detail}
            continue
        if tag == "700":
            detail = score_700(gold, payload)
            if detail is not None:
                scores[tag] = {"score": detail["score"], "detail": detail}
            continue

        row = v1_result[tag]
        if not row["gold_present"]:
            continue
        score = row["f1"] if tag == "653" else row["score"]
        scores[tag] = {"score": float(score or 0.0), "detail": {"status": row["status"]}}
    return scores


# ---------------------------------------------------------------------------
# B. 규칙 준수율
# ---------------------------------------------------------------------------
# 각 검사는 해당 없음이면 None, 해당하면 실패 메시지 목록(빈 목록 = 통과)을 돌려준다.


@dataclass(frozen=True)
class Rule:
    rule_id: str
    label: str
    rag_ref: str
    check: Callable[[dict[str, Any]], list[str] | None]


def _check_subfield_codes(payload: dict[str, Any]) -> list[str] | None:
    applicable = False
    failures: list[str] = []
    for tag, allowed in v1.ALLOWED_SUBFIELD_CODES.items():
        for field in raw_fields(payload, tag):
            applicable = True
            # 245$c는 R-245가 따로 센다. 같은 오류를 두 번 감점하지 않는다.
            failures.extend(
                f"{tag}${code}" for code in raw_codes(field) if code not in allowed and not (tag == "245" and code == "c")
            )
    return failures if applicable else None


def _check_245_structure(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "245")
    if not fields:
        return None
    failures: list[str] = []
    if len(fields) > 1:
        failures.append(f"245 {len(fields)}회 생성")
    for field in fields:
        if not raw_values(field, "a"):
            failures.append("245$a 누락")
        if raw_values(field, "c"):
            failures.append("245$c 사용(책임표시는 $d/$e)")
        if raw_values(field, "h"):
            failures.append("245$h 오용")
        if str(field.get("indicator1", " ")) != "0":
            failures.append(f"245 제1지시기호 {field.get('indicator1')!r}")
    return failures


def _check_020(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "020")
    if not fields:
        return None
    failures: list[str] = []
    for field in fields:
        for value in raw_values(field, "a"):
            if not v1.extract_normalized_isbns([value]):
                failures.append(f"020$a 유효하지 않은 ISBN {value}")
        failures.extend(f"020$g 5자리 아님 {value}" for value in raw_values(field, "g") if not ISBN_ADD_CODE_RE.match(value))
    return failures


def _check_260(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "260")
    if not fields:
        return None
    return ["260$a 발행지 추정" for field in fields if raw_values(field, "a")]


def _check_300(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "300")
    if not fields:
        return None
    failures: list[str] = []
    for field in fields:
        if raw_values(field, "b"):
            failures.append("300$b 근거 없는 기타형태사항")
        for value in raw_values(field, "a"):
            if MEANINGLESS_PAGE_RE.match(value):
                failures.append(f"300$a 무의미값 {value}")
            elif not PAGE_UNIT_RE.search(value):
                failures.append(f"300$a 단위 없음 {value}")
        failures.extend(f"300$c cm 아님 {value}" for value in raw_values(field, "c") if not SIZE_UNIT_RE.search(value))
    return failures


def _check_class_numbers(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "056") + raw_fields(payload, "082")
    if not fields:
        return None
    return [
        f"{field['tag']}$a 형식 {value}"
        for field in fields
        for value in raw_values(field, "a")
        if not KDC_DDC_RE.match(value.strip())
    ]


def _check_490(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "490")
    if not fields:
        return None
    has_830 = bool(raw_fields(payload, "830"))
    return ["490 제1지시기호 1인데 830 없음" for field in fields if str(field.get("indicator1")) == "1" and not has_830]


def _check_policy_excluded(payload: dict[str, Any]) -> list[str] | None:
    return [f"{tag} 정책 제외 필드 생성" for tag in POLICY_EXCLUDED_TAGS if raw_fields(payload, tag)]


def _check_041(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "041")
    if not fields:
        return None
    failures: list[str] = []
    for field in fields:
        codes = set(raw_codes(field))
        for code in ("a", "b", "f", "h", "k"):
            for value in raw_values(field, code):
                if value == "und":
                    failures.append(f"041${code} und 자동 입력")
                elif not LANG_CODE_RE.match(value):
                    failures.append(f"041${code} 형식 {value}")
        if codes <= {"a"} and str(field.get("indicator1")) != "1":
            failures.append("041 본문언어만 기술(번역 정황 없음)")
        if str(field.get("indicator2")) == "7" and "2" not in codes:
            failures.append("041 제2지시기호 7인데 $2 없음")
    return failures


def _check_546(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "546")
    if not fields:
        return None
    failures: list[str] = []
    for field in fields:
        for value in raw_values(field, "a"):
            if NEGATED_NOTE_RE.search(value):
                failures.append(f"546 근거 없음을 서술 '{value}'")
            elif GENERIC_546_RE.match(value) and not TRANSLATION_NOTE_RE.search(value):
                failures.append(f"546 단일 언어 추정 '{value}'")
    return failures


def _check_041_546_consistency(payload: dict[str, Any]) -> list[str] | None:
    translation_546 = [
        value
        for field in raw_fields(payload, "546")
        for value in raw_values(field, "a")
        if TRANSLATION_NOTE_RE.search(value) and not NEGATED_NOTE_RE.search(value)
    ]
    if not translation_546:
        return None
    translated_041 = any(str(field.get("indicator1")) == "1" for field in raw_fields(payload, "041"))
    return [] if translated_041 else ["546은 번역인데 041 번역 표시 없음"]


def _check_500(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "500")
    if not fields:
        return None
    return [
        f"500 언어정보(546/041 우선) '{value}'"
        for field in fields
        for value in raw_values(field, "a")
        if TRANSLATION_ONLY_500_RE.match(value.strip())
    ]


def _check_700_form(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "700")
    if not fields:
        return None
    failures: list[str] = []
    for field in fields:
        names = raw_values(field, "a")
        if len(names) != 1:
            failures.append(f"700$a {len(names)}개")
        for name in names:
            raw_tokens = [token for token in v1.NAME_SPLIT_RE.split(name) if token]
            if any(token in ROLE_TOKENS for token in raw_tokens):
                failures.append(f"700$a 역할어 포함 '{name}'")
            if MULTI_NAME_RE.search(name) or name.count(",") > 1:
                failures.append(f"700$a 여러 사람 '{name}'")
    return failures


def _check_700_matches_245(payload: dict[str, Any]) -> list[str] | None:
    responsibility = set()
    for field in raw_fields(payload, "245"):
        for code in ("d", "e"):
            for value in raw_values(field, code):
                responsibility.update(name_tokens(value))
    if not responsibility:
        return None
    person_tokens = {token for field in raw_fields(payload, "700") for value in raw_values(field, "a") for token in name_tokens(value)}
    missing = sorted(responsibility - person_tokens)
    extra = sorted(person_tokens - responsibility)
    failures = []
    if missing:
        failures.append(f"245 책임표시 인명이 700에 없음 {missing}")
    if extra:
        failures.append(f"245에 없는 인명을 700에 추가 {extra}")
    return failures


def _check_710(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "710")
    if not fields:
        return None
    publishers = [compact_key(value) for field in raw_fields(payload, "260") for value in raw_values(field, "b")]
    publishers = [publisher for publisher in publishers if publisher]
    failures: list[str] = []
    for field in fields:
        roles = {value.strip() for value in raw_values(field, "e")}
        for name in raw_values(field, "a"):
            key = compact_key(name)
            if roles & PUBLISHER_ROLE_VALUES or any(key and (key in pub or pub in key) for pub in publishers):
                failures.append(f"710 출판사를 단체저자로 '{name}'")
    return failures


def _check_246(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "246")
    if not fields:
        return None
    titles: set[str] = set()
    for field in raw_fields(payload, "245"):
        main = "".join(raw_values(field, "a"))
        titles.add(compact_key(main))
        titles.add(compact_key(main + "".join(raw_values(field, "b"))))
    titles.discard("")
    return [
        f"246이 245 본표제와 같음 '{value}'"
        for field in fields
        for value in raw_values(field, "a")
        if compact_key(value) in titles
    ]


def _check_inference_evidence(payload: dict[str, Any]) -> list[str] | None:
    fields = [field for field in payload.get("fields", []) if isinstance(field, dict) and field.get("source") == "ai_inference"]
    if not fields:
        return None
    failures: list[str] = []
    for field in fields:
        evidence = field.get("evidence")
        if not isinstance(evidence, dict) or not evidence.get("from"):
            failures.append(f"{field.get('tag')} evidence.from 없음")
        if field.get("review_required") is not True:
            failures.append(f"{field.get('tag')} review_required 아님")
    return failures


def _check_653_evidence(payload: dict[str, Any]) -> list[str] | None:
    fields = raw_fields(payload, "653")
    if not fields:
        return None
    failures: list[str] = []
    for field in fields:
        evidence = field.get("evidence") if isinstance(field.get("evidence"), dict) else {}
        # 정보나루 키워드를 근거로 썼다면 사용한 키워드를 남겨야 한다.
        if "keywords" in (evidence.get("from") or []) and not evidence.get("keywords_used"):
            failures.append("653 evidence.keywords_used 없음")
        terms = [compact_key(value) for value in raw_values(field, "a")]
        if len(terms) != len(set(terms)):
            failures.append("653 중복 키워드")
    return failures


RULES: tuple[Rule, ...] = (
    Rule("S-codes", "허용 식별기호만 사용", "KORMARC 통합서지 020/041/056/082/245/260/300", _check_subfield_codes),
    Rule("R-020", "ISBN·부가기호 형식", "kormarc.field.020.subfields/forbidden", _check_020),
    Rule("R-245", "245 구조(반복·$a·$c/$h 금지·지시기호 0)", "kormarc.field.245.forbidden/indicators", _check_245_structure),
    Rule("R-260", "발행지 추정 금지", "kormarc.field.260.forbidden", _check_260),
    Rule("R-300", "300 단위·$b 금지·무의미값 금지", "kormarc.field.300.generation/forbidden", _check_300),
    Rule("R-056/082", "분류기호 형식", "kormarc.field.056/082.generation", _check_class_numbers),
    Rule("R-490", "490 제1지시기호 1은 830과 함께", "kormarc.field.490.forbidden", _check_490),
    Rule("R-policy", "650·830·950 자동 생성 금지", "kormarc.field.650/490.generation, 기관 로컬 정책", _check_policy_excluded),
    Rule("R-041", "041 부호 형식·번역 정황", "kormarc.field.041.generation/indicators", _check_041),
    Rule("R-546", "546 무근거 언어주기 금지", "kormarc.field.546.generation", _check_546),
    Rule("R-041/546", "546 번역 주기와 041 번역 표시 일관", "kormarc.field.546.generation", _check_041_546_consistency),
    Rule("R-500", "언어정보를 500에 쓰지 않음", "kormarc.field.500.generation/validation", _check_500),
    Rule("R-700-form", "700은 1인 1필드, 역할어는 $e", "kormarc.field.700.generation", _check_700_form),
    Rule("R-700-245", "700 인원 = 245 책임표시 인원", "kormarc.field.700.generation", _check_700_matches_245),
    Rule("R-710", "출판사를 710에 올리지 않음", "kormarc.field.710.skip", _check_710),
    Rule("R-246", "245와 같은 표제를 246으로 만들지 않음", "kormarc.field.246.skip", _check_246),
    Rule("R-evidence", "추론 필드는 evidence·검수 표시 필수", "kormarc.field.500/653/041.validation", _check_inference_evidence),
    Rule("R-653", "653 사용 키워드 기록·중복 없음", "kormarc.field.653.generation", _check_653_evidence),
)


def rule_results(payload: dict[str, Any]) -> dict[str, list[str] | None]:
    return {rule.rule_id: rule.check(payload) for rule in RULES}


# ---------------------------------------------------------------------------
# C. 생성 판단
# ---------------------------------------------------------------------------


def decision_outcomes(gold: v1.RecordData, payload: dict[str, Any]) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for tag in DECISION_TAGS:
        gold_present = gold_has_tag(gold, tag)
        generated = bool(raw_fields(payload, tag))
        if gold_present and generated:
            outcomes[tag] = "TP"
        elif gold_present:
            outcomes[tag] = "FN"
        elif generated:
            outcomes[tag] = "FP"
        else:
            outcomes[tag] = "TN"
    return outcomes


# ---------------------------------------------------------------------------
# 집계
# ---------------------------------------------------------------------------


def evaluate_run(gold_records: list[v1.RecordData], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    books: list[dict[str, Any]] = []
    for gold in gold_records:
        payload = results.get(gold.isbn)
        if payload is None:
            continue
        books.append(
            {
                "isbn": gold.isbn,
                "values": value_scores(gold, payload),
                "rules": rule_results(payload),
                "decisions": decision_outcomes(gold, payload),
            }
        )

    field_rows = []
    all_scores: list[float] = []
    for tag in VALUE_FIELDS:
        scores = [book["values"][tag]["score"] for book in books if tag in book["values"]]
        all_scores.extend(scores)
        field_rows.append(
            {
                "field": tag,
                "gold_books": len(scores),
                "mean_score": safe_ratio(sum(scores), len(scores)),
                "exact_rate": safe_ratio(sum(1 for score in scores if score >= 1.0), len(scores)),
            }
        )

    rule_rows = []
    rule_pass = rule_total = 0
    for rule in RULES:
        outcomes = [book["rules"][rule.rule_id] for book in books if book["rules"][rule.rule_id] is not None]
        passed = sum(1 for failures in outcomes if not failures)
        rule_pass += passed
        rule_total += len(outcomes)
        rule_rows.append(
            {
                "rule": rule.rule_id,
                "label": rule.label,
                "rag_ref": rule.rag_ref,
                "applicable_books": len(outcomes),
                "passed_books": passed,
                "pass_rate": safe_ratio(passed, len(outcomes)),
            }
        )
    clean_books = sum(1 for book in books if not any(book["rules"][rule.rule_id] for rule in RULES))

    decision_rows = []
    totals = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    for tag in DECISION_TAGS:
        counts = {key: sum(1 for book in books if book["decisions"][tag] == key) for key in totals}
        for key, value in counts.items():
            totals[key] += value
        decision_rows.append(
            {
                "tag": tag,
                **counts,
                "decision_accuracy": safe_ratio(counts["TP"] + counts["TN"], len(books)),
                "overgeneration_rate": safe_ratio(counts["FP"], counts["FP"] + counts["TN"]),
                "omission_rate": safe_ratio(counts["FN"], counts["TP"] + counts["FN"]),
            }
        )

    axis_a = safe_ratio(sum(all_scores), len(all_scores))
    axis_b = safe_ratio(rule_pass, rule_total)
    axis_c = safe_ratio(totals["TP"] + totals["TN"], sum(totals.values()))
    axes = [value for value in (axis_a, axis_b, axis_c) if value is not None]

    v1_rows = v1.build_summary_rows(
        [v1.compare_record(gold, results[gold.isbn], allow_partial_653=True) for gold in gold_records if gold.isbn in results]
    )
    v1_overall = next(row for row in v1_rows if row["field"] == "OVERALL")

    scorecard = {
        "books": len(books),
        "A_value_accuracy": axis_a,
        "A_exact_rate": safe_ratio(sum(1 for score in all_scores if score >= 1.0), len(all_scores)),
        "B_rule_compliance": axis_b,
        "B_clean_record_rate": safe_ratio(clean_books, len(books)),
        "C_decision_accuracy": axis_c,
        "C_overgeneration_rate": safe_ratio(totals["FP"], totals["FP"] + totals["TN"]),
        "C_omission_rate": safe_ratio(totals["FN"], totals["TP"] + totals["FN"]),
        "KOMA_Q": round(sum(axes) / len(axes), 4) if axes else None,
        "v1_completeness": v1_overall["completeness"],
        "v1_accuracy": v1_overall["accuracy"],
    }

    return {
        "scorecard": scorecard,
        "fields": field_rows,
        "rules": rule_rows,
        "decisions": decision_rows,
        "books": books,
        "detail_245": _detail_245(books),
    }


def _detail_245(books: list[dict[str, Any]]) -> dict[str, Any]:
    components: dict[str, list[float]] = {"title": [], "subtitle": [], "responsibility": []}
    for book in books:
        detail = book["values"].get("245", {}).get("detail", {})
        for name, value in detail.get("components", {}).items():
            components[name].append(value)
    return {name: {"books": len(values), "mean": safe_ratio(sum(values), len(values))} for name, values in components.items()}


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def pct(value: float | None) -> str:
    return "–" if value is None else f"{value * 100:.1f}"


SCORECARD_LABELS = (
    ("KOMA_Q", "KOMA-Q 종합 (A·B·C 평균)"),
    ("A_value_accuracy", "A 값 정확도 (부분점수 평균)"),
    ("A_exact_rate", "A 값 exact 비율"),
    ("B_rule_compliance", "B RAG 규칙 준수율"),
    ("B_clean_record_rate", "B 규칙 위반 0건 레코드 비율"),
    ("C_decision_accuracy", "C 생성/보류 판단 정확도"),
    ("C_overgeneration_rate", "C 과잉 생성률 (낮을수록 좋음)"),
    ("C_omission_rate", "C 누락률 (낮을수록 좋음)"),
    ("v1_completeness", "(참고) v1 완전성"),
    ("v1_accuracy", "(참고) v1 정확도"),
)


def build_report(runs: dict[str, dict[str, Any]]) -> str:
    names = list(runs)
    header = "| 지표 | " + " | ".join(names) + " |"
    divider = "|---|" + "---:|" * len(names)
    lines = [
        f"# KOMA 평가 v2 결과 ({EVALUATOR_VERSION})",
        "",
        "모든 실행을 같은 평가기로 채점했다. 수치는 % 단위다.",
        "",
        "## 종합",
        "",
        header,
        divider,
    ]
    for key, label in SCORECARD_LABELS:
        lines.append(f"| {label} | " + " | ".join(pct(runs[name]["scorecard"][key]) for name in names) + " |")

    lines += ["", "## A. 필드별 값 정확도 (gold 보유 도서 기준, 부분점수 평균 / exact)", "", header, divider]
    for index, row in enumerate(runs[names[0]]["fields"]):
        if not row["gold_books"]:
            continue
        cells = []
        for name in names:
            other = runs[name]["fields"][index]
            cells.append(f"{pct(other['mean_score'])} / {pct(other['exact_rate'])}")
        lines.append(f"| {row['field']} (n={row['gold_books']}) | " + " | ".join(cells) + " |")

    lines += ["", "### 245 성분별", "", header, divider]
    for component in ("title", "subtitle", "responsibility"):
        cells = [
            f"{pct(runs[name]['detail_245'][component]['mean'])} (n={runs[name]['detail_245'][component]['books']})" for name in names
        ]
        lines.append(f"| {component} | " + " | ".join(cells) + " |")

    lines += ["", "## B. RAG 규칙 준수 (통과 도서 / 해당 도서)", "", "| 규칙 | 내용 | " + " | ".join(names) + " |", "|---|---|" + "---:|" * len(names)]
    for index, row in enumerate(runs[names[0]]["rules"]):
        cells = []
        for name in names:
            other = runs[name]["rules"][index]
            cells.append("–" if not other["applicable_books"] else f"{other['passed_books']}/{other['applicable_books']}")
        lines.append(f"| {row['rule']} | {row['label']} | " + " | ".join(cells) + " |")

    lines += ["", "## C. 생성 판단 (TP·TN·FP·FN)", "", "| 태그 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for index, row in enumerate(runs[names[0]]["decisions"]):
        cells = []
        for name in names:
            other = runs[name]["decisions"][index]
            cells.append(f"TP {other['TP']} · TN {other['TN']} · FP {other['FP']} · FN {other['FN']}")
        lines.append(f"| {row['tag']} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## 채점 규칙 요약",
        "",
        "- A: gold가 있는 (도서, 필드)가 분모다. 생성하지 않으면 0점. 653은 F1, 700은 인명 F1(원어명 부출 제외),",
        "  245는 본표제·부제·책임표시 성분 평균(역할어는 토큰 단위로 제거), 나머지는 v1 점수를 쓴다.",
        "- B: `ai/rag/chunks`의 generation/forbidden 규칙을 검사로 옮겼다. 해당 필드가 있는 도서만 분모다.",
        "- C: gold 440은 490, gold 650은 653과 같은 것으로 본다. 650·830·950은 B의 정책 제외 규칙에서 본다.",
        "- KOMA-Q = (A + B + C) / 3.",
        "",
    ]
    return "\n".join(lines)


def parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--run은 label=결과디렉터리 형식이어야 합니다")
    label, path = value.split("=", 1)
    return label.strip(), Path(path.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KOMA 생성 결과를 RAG 규칙 기반 v2 기준으로 채점하고 실행 간 비교한다.")
    parser.add_argument("--run", type=parse_run, action="append", required=True, help="label=결과디렉터리 (여러 번 지정)")
    parser.add_argument("--gold-mrc", type=Path, default=v1.DEFAULT_GOLD_MRC)
    parser.add_argument("--out-dir", type=Path, default=v1.ROOT_DIR / "ai" / "evaluation" / "runs" / "v2-compare")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gold_records = v1.parse_gold_records(args.gold_mrc)
    if not gold_records:
        raise SystemExit(f"No MARC records parsed from {args.gold_mrc}")

    runs: dict[str, dict[str, Any]] = {}
    for label, results_dir in args.run:
        results = v1.load_koma_results(results_dir)
        if not results:
            raise SystemExit(f"결과가 없습니다: {results_dir}")
        runs[label] = evaluate_run(gold_records, results)
        runs[label]["results_dir"] = str(results_dir)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "v2_scorecard.csv", [{"run": name, **run["scorecard"]} for name, run in runs.items()])
    write_csv(out_dir / "v2_fields.csv", [{"run": name, **row} for name, run in runs.items() for row in run["fields"]])
    write_csv(out_dir / "v2_rules.csv", [{"run": name, **row} for name, run in runs.items() for row in run["rules"]])
    write_csv(out_dir / "v2_decisions.csv", [{"run": name, **row} for name, run in runs.items() for row in run["decisions"]])
    write_csv(
        out_dir / "v2_books.csv",
        [
            {
                "run": name,
                "isbn": book["isbn"],
                **{f"A_{tag}": book["values"][tag]["score"] if tag in book["values"] else "" for tag in VALUE_FIELDS},
                "B_failures": " | ".join(f"{rule}: {'; '.join(failures)}" for rule, failures in book["rules"].items() if failures),
                "C_FP": ",".join(tag for tag, outcome in book["decisions"].items() if outcome == "FP"),
                "C_FN": ",".join(tag for tag, outcome in book["decisions"].items() if outcome == "FN"),
            }
            for name, run in runs.items()
            for book in run["books"]
        ],
    )
    (out_dir / "v2_details.json").write_text(
        json.dumps({"evaluator_version": EVALUATOR_VERSION, "gold_mrc": args.gold_mrc.name, "runs": runs}, ensure_ascii=False, indent=2, default=list),
        encoding="utf-8",
    )
    report = build_report(runs)
    (out_dir / "REPORT.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
