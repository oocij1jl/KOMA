# 041 언어부호

## Metadata

- `chunk_group`: `kormarc.field.041`
- `tag`: `041`
- `field_name`: `언어부호`
- `field_priority`: `conditional`
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/01X_09X_041.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-06-16`

## Purpose

041 필드는 008/35-37 언어부호만으로 언어 정보를 충분히 표현할 수 없을 때 자료와 관련된 언어를 3자리 부호로 기술하는 필드이다.

이 서비스에서는 번역서, 다국어 자료, 요약/초록/목차/자막 등 별도 언어 정보가 evidence에서 확인될 때만 조건부로 생성한다.

## Official KORMARC Summary

- 반복 가능 필드이다.
- 해당 시 필수 성격의 필드이다.
- 제1지시기호는 번역물 여부를 나타낸다.
- 제2지시기호는 언어부호 정보원을 나타낸다.
- 언어부호는 일반적으로 부속서 언어구분부호표의 3자리 소문자 부호를 사용한다.
- 번역물에는 번역 언어와 원저작 언어를 구분하여 기술한다.
- 언어사항은 문장형 주기로 546 필드에도 기술할 수 있다.

## Evidence Mapping

`field_evidence_map["041"] = ["translation_signals", "description", "author"]`

| Evidence | Use |
|---|---|
| `evidence.translation_signals` | 번역 정황 1차 힌트 |
| `evidence.description` | 번역, 원저자, 원어, 다국어 정황 확인 |
| `evidence.author` | `옮김`, `역`, 원저자 패턴 확인 |
| `evidence.available.description` | false이면 description은 근거로 사용하지 않음 |

## Indicators

### Indicator 1: Translation Indicator

| Value | Meaning | Service Use |
|---|---|---|
| ` ` | 해당정보 없음 | 번역 여부가 불명확하면 사용하되 생성 자체를 보류하는 것이 우선 |
| `0` | 번역물이 아니거나 번역물을 포함하지 않음 | 다국어지만 번역물이 아님이 명확할 때 |
| `1` | 번역물이거나 번역물을 포함 | 번역 정황이 명확할 때 |

### Indicator 2: Code Source

| Value | Meaning | Service Use |
|---|---|---|
| ` ` | 언어구분표 | 3자리 MARC 언어부호 사용 시 기본값 |
| `7` | `2` 식별기호에 정보원 직접 입력 | 다른 언어부호 정보원을 확정할 때만 사용 |

## Subfields

| Code | Meaning | Repeatable | Service Use |
|---|---|---|---|
| `a` | 본문언어/사운드트랙 언어 | yes | 번역 후 본문 언어 등 |
| `b` | 요약문/초록 언어 | yes | evidence에 명확할 때만 |
| `d` | 노래 또는 말로 된 본문 언어 | yes | 녹음/음악자료에 한정 |
| `h` | 원저작의 언어 | yes | 원어가 명확할 때만 |
| `k` | 중역의 언어 | yes | 중역 정황이 명확할 때만 |
| `j` | 자막 언어 | yes | 시청각자료에 한정 |
| `2` | 부호의 정보원 | no | indicator2가 `7`일 때만 |
| `6` | 대체문자 연결 | no | MVP에서는 생성하지 않음 |
| `8` | 필드 링크와 일련번호 | yes | MVP에서는 생성하지 않음 |

## Service Generation Rule

1. `evidence.translation_signals.detected=true`이거나 `evidence.description`, `evidence.author`에서 번역 정황이 명확할 때만 041 생성을 고려한다.
2. 정황만 있고 언어부호를 확정할 수 없으면 041을 생성하지 않는다.
3. 한국어 번역본임이 명확하면 `a=kor` 후보를 사용할 수 있다.
4. 원저작 언어가 명확하게 나타난 경우에만 `h`를 사용한다.
5. 원저작 언어를 모르면 `h=und`를 자동 생성하지 않는다. 모르는 값은 skipped로 둔다.
6. 언어부호는 소문자 3자리로 기술한다.
7. 생성 시 `source="ai_inference"`, `review_required=true`를 부여한다.
8. 문장형 언어 설명은 546에 두고, 041에는 부호만 넣는다.

## JSON Output Rule

```json
{
  "tag": "041",
  "indicator1": "1",
  "indicator2": " ",
  "subfields": [
    { "code": "a", "value": "kor" },
    { "code": "h", "value": "eng" }
  ],
  "source": "ai_inference",
  "review_required": true,
  "confidence": "medium",
  "note": "번역 정황 기반 언어부호 제안. 언어부호 검수 필요",
  "evidence": {
    "from": ["translation_signals", "description", "author"],
    "reasoning": "저자 표시와 책소개에서 영어 원작의 한국어 번역 정황 확인"
  }
}
```

## Skip Rule

| Condition | Reason |
|---|---|
| 번역/다국어 정황이 없음 | `번역 또는 다국어 정황 없음: 041 생성 조건 미충족` |
| 언어명은 있으나 3자리 언어부호를 확정할 수 없음 | `언어부호 미확정: 041 생성 보류` |
| 원저작 언어가 명확하지 않음 | `원저작 언어 미확정: 041 h 생성 금지` |
| `evidence.available.description=false`이고 `translation_signals` 힌트도 없으며 `author`에도 번역 정황이 없음 | `근거 부족: 041 생성에 필요한 evidence 미수집` |

## Risk and Validation

- 041은 조건부 필드이다.
- 생성 시 항상 `review_required=true`로 둔다.
- 언어부호는 소문자 3자리여야 한다.
- `indicator2="7"`이면 `2` 식별기호가 필수이다.
- `source="ai_inference"`이면 `evidence` 객체가 필수이다.
- 041과 546은 서로 일관되어야 한다.

## Retrieval Hints

- 041 언어부호
- 번역물 표시
- translation_signals
- 원저작 언어
- kor eng h
- 언어부호 소문자
