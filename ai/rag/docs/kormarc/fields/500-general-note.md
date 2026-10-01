# 500 일반주기

## Metadata

- `chunk_group`: `kormarc.field.500`
- `tag`: `500`
- `field_name`: `일반주기`
- `field_priority`: `conditional`
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/5XX_500.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-06-16`

## Purpose

500 필드는 특정 5XX 주기 필드에 해당하지 않는 일반 정보를 기술하는 주기 필드이다. 이 서비스에서는 책소개나 번역 정황에서 일반주기로 남길 필요가 명확한 경우에만 조건부로 생성한다.

500은 자유롭게 아무 설명이나 넣는 필드가 아니다. 더 적합한 특정 주기 필드가 있으면 해당 필드를 우선한다.

## Official KORMARC Summary

- 반복 가능 필드이다.
- 재량 필드이다.
- 제1지시기호와 제2지시기호는 미정의이므로 공백으로 표시한다.
- 주요 식별기호는 `a`이며 일반주기를 기술한다.
- 501-59X의 특정 주기 필드에 해당하지 않는 일반 정보를 기술한다.
- 특정 주기 필드에 해당하는 경우에는 해당 주기 필드에 우선 기술한다.
- 약어로 끝나는 경우를 제외하고 필드 끝에 구두점을 사용하지 않는다.

## Evidence Mapping

`field_evidence_map["500"] = ["translation_signals", "description", "author"]`

| Evidence | Use |
|---|---|
| `evidence.translation_signals` | 원저작/번역 관련 일반주기 후보 확인 |
| `evidence.description` | 일반주기 후보 문구 근거 |
| `evidence.author` | 옮김/역자/원저자 정황 보조 |
| `evidence.description` | 500 후보 원천이 될 수 있으나 그대로 복사하지 않음 |

## Indicators

| Indicator | Value | Service Use |
|---|---|---|
| `indicator1` | ` ` | 미정의. 항상 공백 |
| `indicator2` | ` ` | 미정의. 항상 공백 |

## Subfields

| Code | Meaning | Repeatable | Service Use |
|---|---|---|---|
| `a` | 일반주기 | no | 일반주기 문장 |
| `3` | 자료 범위지정 | no | 특정 범위에만 해당할 때 |
| `5` | 필드 적용 기관 | no | 자동 생성하지 않음 |
| `6` | 대체문자 연결 | no | MVP에서는 생성하지 않음 |
| `8` | 필드 링크와 일련번호 | yes | MVP에서는 생성하지 않음 |

## Service Generation Rule

1. 500은 조건부 필드이며, 근거가 명확할 때만 생성한다.
2. 특정 주기 필드가 더 적합하면 500을 사용하지 않는다. 언어 설명은 546, 언어부호는 041을 우선한다.
3. 번역 관련 원저자/원표제 주기는 `evidence.translation_signals`, `evidence.description`, `evidence.author`에서 명확히 확인될 때만 제안한다.
4. 책소개 전체를 500에 그대로 복사하지 않는다.
5. 근거 없는 원저자명, 원표제, 부록, 색인 여부를 만들지 않는다.
6. 생성 시 `source="ai_inference"`, `review_required=true`를 부여한다.
7. API에서 명시적으로 제공된 설명을 단순 표시하는 것과 MARC 500 생성은 구분한다.

## JSON Output Rule

```json
{
  "tag": "500",
  "indicator1": " ",
  "indicator2": " ",
  "subfields": [
    { "code": "a", "value": "원저자명은 책소개에 기재된 정보를 따름" }
  ],
  "source": "ai_inference",
  "review_required": true,
  "confidence": "low",
  "note": "책소개 기반 일반주기 후보. 원문 확인 필요",
  "evidence": {
    "from": ["translation_signals", "description", "author"],
    "reasoning": "책소개에 원저작 또는 번역 관련 정황이 명시되어 일반주기 후보로 제안"
  }
}
```

## Skip Rule

| Condition | Reason |
|---|---|
| 특정 5XX 필드가 더 적합함 | `500보다 특정 주기 필드 우선` |
| 책소개만 있고 일반주기로 옮길 명확한 사실이 없음 | `일반주기 근거 부족: description 단순 복사 금지` |
| 원저자명/원표제가 추정일 뿐임 | `원저작 정보 미확정: 500 생성 금지` |
| `evidence.available.description=false`이고 `translation_signals` 힌트도 없으며 `author`에도 주기 근거가 없음 | `근거 부족: 500 생성에 필요한 evidence 미수집` |

## Risk and Validation

- 500은 조건부 필드이다.
- 생성 시 항상 `review_required=true`로 둔다.
- `indicator1`, `indicator2`는 공백이어야 한다.
- `source="ai_inference"`이면 `evidence` 객체가 필수이다.
- 책소개를 장문으로 그대로 복사하지 않는다.
- `value`에는 필드 종단 구두점을 임의로 넣지 않는다.
- 546, 041 등 더 구체적인 필드와 중복되면 경고한다.

## Retrieval Hints

- 500 일반주기
- description 단순 복사 금지
- 원저자 주기
- 번역 정황
- 특정 주기 필드 우선
- review_required note
