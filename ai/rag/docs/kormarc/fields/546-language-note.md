# 546 언어주기

## Metadata

- `chunk_group`: `kormarc.field.546`
- `tag`: `546`
- `field_name`: `언어주기`
- `field_priority`: `conditional`
- `generation_path`: `llm` (evidence 기반 LLM 추론. 검증 단계가 근거 없는 생성을 제거한다)
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/5XX_546.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-09-24`

## Purpose

546은 자료에 사용된 언어에 관한 사항을 문장으로 기술하는 재량 반복 필드다. 언어부호는 008/35-37과 041에 기술하고 546에는 사람이 읽는 설명을 둔다.

## Indicators

제1지시기호와 제2지시기호는 미정의이므로 항상 공백이다.

## Subfields

허용 식별기호는 a 언어주기(반복불가), b 언어 부호 또는 알파벳 정보, 3, 6, 8이다.

## Service Generation Rule

번역, 원작 언어, 대역, 병기, 자막, 요약·초록 언어처럼 본문 언어 외의 언어 정보가 evidence에서 확인될 때만 만든다. 번역 정황이 있으면 041과 일관되게 만든다. 문장형 설명만 a에 넣는다.

## Skip Rule

'한국어로 된 자료', '한국어로 기술된 자료'처럼 단일 언어 추정만 담은 주기는 만들지 않는다. 자료가 한국어라는 사실은 008/35-37이 담당한다. 검증 단계에서도 번역·원작·대역·병기·자막·요약 같은 언어 정보가 없으면 제거하고 '언어주기 근거 없음: 단일 언어 추정만으로 생성 금지'를 남긴다.

## Risk and Validation

546은 조건부 필드이며 생성 시 review_required=true다. 지시기호는 공백이어야 한다. source가 ai_inference면 evidence가 필수다. 041 언어부호와 546 문장 설명이 충돌하면 경고한다.

## Retrieval Hints

- 546 정의
- 언어주기
- 546 지시기호
- 546 식별기호
- 546 생성
- 번역 설명
- 원작 언어
- 546 skipped
- 한국어로 된 자료 금지
- 단일 언어
- 546 검증
- 041 일관성
