# 653 비통제 색인어

## Metadata

- `chunk_group`: `kormarc.field.653`
- `tag`: `653`
- `field_name`: `비통제 색인어`
- `field_priority`: `review_required`
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/6XX_653.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-06-16`

## Purpose

653 필드는 표준 주제명표목표나 시소러스의 통제 규칙으로 확정되지 않은 색인어를 기술하는 주제 접근 필드이다.

이 서비스에서는 정보나루 `keywordList`의 자유 키워드를 근거로 주제 접근점을 제안할 때 653을 주력 필드로 사용한다. 이는 자유 키워드를 통제 주제명인 650으로 임의 승격하지 않기 위한 보수적 정책이다.

## Official KORMARC Summary

- 반복 가능 필드이다.
- 해당 시 필수 성격의 필드이다.
- 제1지시기호는 색인어 수준을 나타낸다.
- 제2지시기호는 용어나 이름의 유형을 나타낸다.
- 주요 식별기호는 `a`이며, 비통제 색인어를 반복해서 기술할 수 있다.
- 같은 수준과 같은 유형의 색인어가 여러 개이면 `a`를 반복할 수 있다.
- 유형이 서로 다르면 한 필드에서 `a`를 반복하지 말고 653 필드를 나누는 것이 안전하다.
- 일반적인 653 데이터에는 종단 구두점을 붙이지 않는다. 단, 약자, 두문자, 자체 구두점이 있는 값은 예외가 될 수 있다.

## Indicators

### Indicator 1: Index Term Level

| Value | Meaning | Service Use |
|---|---|---|
| ` ` | 해당정보 없음 | 기본값. 정보나루 키워드에서 수준 판단 근거가 없을 때 사용 |
| `0` | 수준 없음 | 수준 판단은 가능하지만 구체적 수준이 없을 때만 사용 |
| `1` | 1차 수준 | 핵심 주제라는 근거가 명확할 때만 사용 |
| `2` | 2차 수준 | 부차 주제라는 근거가 명확할 때만 사용 |

### Indicator 2: Term or Name Type

| Value | Meaning | Service Use |
|---|---|---|
| ` ` | 해당정보 없음 | 기본값. 키워드 유형 판단 근거가 부족할 때 사용 |
| `0` | 주제명 | 일반 주제어라고 판단 가능할 때만 사용 |
| `1` | 개인명 | 인명 근거가 명확할 때만 사용 |
| `2` | 단체명 | 단체명 근거가 명확할 때만 사용 |
| `3` | 회의명 | 회의명 근거가 명확할 때만 사용 |
| `4` | 연대용어 | 시대/연대 표현이 명확할 때만 사용 |
| `5` | 지명 | 지명 근거가 명확할 때만 사용 |
| `6` | 장르/형식 용어 | 장르나 형식 용어가 명확할 때만 사용 |

## Subfields

| Code | Meaning | Repeatable | Service Use |
|---|---|---|---|
| `a` | 비통제 색인어 | yes | 정보나루 키워드 기반 색인어 |
| `6` | 대체문자 연결 | no | MVP에서는 생성하지 않음 |
| `8` | 필드 링크와 일련번호 | yes | MVP에서는 생성하지 않음 |

## Service Generation Rule

1. `evidence.available.keywords=true`이면 `evidence.keywords`의 가중치 상위 키워드를 우선 후보로 삼는다.
2. `evidence.description`과 `evidence.co_loan_books`는 키워드 후보의 주제 적합성을 보조 확인하는 데만 사용한다.
3. 키워드 값은 의미를 바꾸지 않는 범위에서 최소 정제한다.
4. 조사, 불필요한 공백, 명백한 중복만 제거한다.
5. 표준 주제명표목표 대조 없이 650으로 승격하지 않는다.
6. 공식 KORMARC에는 653의 제2지시기호 유형 코드가 있으므로, 유형 판단 근거가 없으면 `indicator2`는 공백으로 둔다.
7. 수준 판단 근거가 없으면 `indicator1`도 공백으로 둔다.
8. 생성된 653은 추론 필드이므로 `source="ai_inference"`, `review_required=true`를 부여한다.
9. 사용한 키워드는 출력 필드의 `evidence.keywords_used`에 기록한다.
10. 653 색인어에서 서명, 저자명, 출판사명, 총서명, 다른 책 제목은 제외한다. 키워드 목록에 이들이 상위로 포함돼 있어도 653 값으로 쓰지 않으며, 주제·소재·장르·개념을 나타내는 키워드만 남긴다.

## JSON Output Rule

```json
{
  "tag": "653",
  "indicator1": " ",
  "indicator2": " ",
  "subfields": [
    { "code": "a", "value": "진화론" },
    { "code": "a", "value": "생물학" }
  ],
  "source": "ai_inference",
  "review_required": true,
  "confidence": "medium",
  "note": "정보나루 키워드 기반 비통제 색인어. 사서 검수 필요",
  "evidence": {
    "from": ["keywords"],
    "keywords_used": ["진화론(0.92)", "생물학(0.81)"],
    "reasoning": "가중치 상위 키워드를 의미 변경 없이 최소 정제하여 653으로 제안"
  }
}
```

## Skip Rule

653을 생성하지 말고 `skipped_fields`에 남긴다.

| Condition | Reason |
|---|---|
| `evidence.available.keywords=false`이고 `evidence.available.description=false`, `evidence.available.co_loan_books=false`임 | `근거 부족: 653 생성에 필요한 evidence 미수집: keywords, description, co_loan_books` |
| 키워드가 서명, 저자명, 출판사명 등 서지 값의 단순 반복뿐임 | `주제 색인어로 사용할 독립 근거 부족` |
| 키워드 의미가 불명확하여 주제 접근점으로 부적절함 | `색인어 의미 검수 필요: 자동 생성 보류` |

## Risk and Validation

- 653은 이 서비스에서 주력 추론 필드지만, 사람이 검수해야 한다.
- `source="ai_inference"`이면 `evidence` 객체가 반드시 있어야 한다.
- `review_required`는 항상 `true`로 둔다.
- `confidence`는 보통 `medium`이며, description/co_loan_books 보조 근거가 부족하면 `low`로 낮춘다.
- `value`에는 종단 구두점, ISBD 구두점, 식별기호 기호를 넣지 않는다.
- 약어나 두문자 자체에 포함된 점은 값의 일부로 허용할 수 있다.

## Retrieval Hints

- 653 생성 조건
- 비통제 색인어
- 정보나루 키워드
- 주제 색인
- 650 대신 653
- 통제 주제명 승격 금지
- review_required subject inference
