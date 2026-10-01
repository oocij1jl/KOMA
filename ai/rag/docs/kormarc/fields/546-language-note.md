# 546 언어주기

## Metadata

- `chunk_group`: `kormarc.field.546`
- `tag`: `546`
- `field_name`: `언어주기`
- `field_priority`: `conditional`
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/5XX_546.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-06-16`

## Purpose

546 필드는 자료에 사용된 언어에 관한 사항을 문장으로 기술하는 주기 필드이다. 이 서비스에서는 번역서, 다국어 자료, 본문 언어와 표제 언어가 다른 경우 등 언어 설명이 evidence에서 확인될 때만 생성한다.

041이 언어를 부호로 표현한다면, 546은 사람이 읽을 수 있는 문장형 언어 설명이다.

## Official KORMARC Summary

- 반복 가능 필드이다.
- 재량 필드이다.
- 제1지시기호와 제2지시기호는 미정의이므로 공백으로 표시한다.
- 주요 식별기호는 `a`이며 언어주기를 기술한다.
- `b` 식별기호에는 언어 부호 또는 알파벳, 문자 체계 정보를 기술할 수 있다.
- 언어부호는 008/35-37과 041 필드에 기술한다.

## Evidence Mapping

`field_evidence_map["546"] = ["description", "title", "author"]`

| Evidence | Use |
|---|---|
| `evidence.description` | 언어, 번역, 원어, 대역, 요약 언어 정황 확인 |
| `evidence.title` | 표제 언어 정황 보조 |
| `evidence.author` | 옮김/역자 표시 보조 |

## Indicators

| Indicator | Value | Service Use |
|---|---|---|
| `indicator1` | ` ` | 미정의. 항상 공백 |
| `indicator2` | ` ` | 미정의. 항상 공백 |

## Subfields

| Code | Meaning | Repeatable | Service Use |
|---|---|---|---|
| `a` | 언어주기 | no | 문장형 언어 설명 |
| `b` | 언어 부호 또는 알파벳 정보 | yes | 문자체계 근거가 있을 때만 |
| `3` | 자료 범위지정 | no | 특정 범위에만 해당할 때 |
| `6` | 대체문자 연결 | no | MVP에서는 생성하지 않음 |
| `8` | 필드 링크와 일련번호 | yes | MVP에서는 생성하지 않음 |

## Service Generation Rule

1. `evidence.description`, `evidence.title`, `evidence.author`에서 언어 관련 정황이 명확할 때만 생성한다.
2. 번역 정황이 있으면 041과 함께 일관되게 생성한다.
3. 문장형 설명만 546 `a`에 넣는다.
4. 언어부호 자체는 041에 넣고, 546에는 사람이 읽는 설명을 넣는다.
5. 근거 없는 원어, 번역 언어, 요약 언어를 만들지 않는다.
6. 단순히 한국어 책이라는 추정만으로 546을 생성하지 않는다.
7. 생성 시 `source="ai_inference"`, `review_required=true`를 부여한다.

## JSON Output Rule

```json
{
  "tag": "546",
  "indicator1": " ",
  "indicator2": " ",
  "subfields": [
    { "code": "a", "value": "영어 원작을 한국어로 번역" }
  ],
  "source": "ai_inference",
  "review_required": true,
  "confidence": "medium",
  "note": "책소개와 저자 표시 기반 언어주기 제안. 사서 검수 필요",
  "evidence": {
    "from": ["description", "author"],
    "reasoning": "책소개와 저자 표시에서 번역 정황 확인"
  }
}
```

## Skip Rule

| Condition | Reason |
|---|---|
| 언어 또는 번역 정황이 없음 | `언어주기 생성 조건 미충족` |
| 원어/번역 언어가 명확하지 않음 | `언어 정보 미확정: 546 생성 보류` |
| `evidence.available.description=false`이고 `title`, `author`에서도 언어 정황이 확인되지 않음 | `근거 부족: 546 생성에 필요한 evidence 미수집` |
| 041만으로 충분하고 문장형 주기 근거가 없음 | `문장형 언어주기 근거 없음` |

## Risk and Validation

- 546은 조건부 필드이다.
- 생성 시 항상 `review_required=true`로 둔다.
- `indicator1`, `indicator2`는 공백이어야 한다.
- `source="ai_inference"`이면 `evidence` 객체가 필수이다.
- 041 언어부호와 546 문장 설명이 충돌하면 경고한다.
- `value`에는 필드 종단 구두점을 임의로 넣지 않는다.

## Retrieval Hints

- 546 언어주기
- 번역 언어 설명
- 문장형 언어주기
- 041과 일관성
- description author translation
