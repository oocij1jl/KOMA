# 041 언어부호

## Metadata

- `chunk_group`: `kormarc.field.041`
- `tag`: `041`
- `field_name`: `언어부호`
- `field_priority`: `conditional`
- `generation_path`: `llm` (evidence 기반 LLM 추론. 검증 단계가 근거 없는 생성을 제거한다)
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/01X_09X_041.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-09-24`

## Purpose

041은 008/35-37의 언어부호만으로 언어 정보를 충분히 표현할 수 없을 때 자료와 관련된 언어를 3자리 부호로 기술하는 해당시필수 반복 필드다. 두 개 이상의 언어를 포함하거나, 번역물이거나, 요약·목차·딸림자료의 언어가 본문과 다를 때 사용한다.

## Indicators

제1지시기호는 번역물 표시로 공백 해당정보 없음, 0 번역물이 아님, 1 번역물이거나 번역물을 포함이다. 제2지시기호는 부호의 정보원으로 공백은 언어구분부호표, 7은 식별기호 2에 정보원을 직접 입력하는 경우다. indicator2가 7이면 2 식별기호가 반드시 있어야 한다.

## Subfields

이 서비스가 쓰는 식별기호는 a 본문언어, b 요약문 언어, f 내용목차 언어, h 원저작의 언어, k 중역의 언어다. 번역물이면 번역된 언어를 a에, 원저작 언어를 h에 기술한다. 언어부호는 알파벳 소문자 3자리다.

## Service Generation Rule

translation_signals.detected가 true이거나 description·author에서 번역 정황이 명확할 때만 041을 만든다. 번역 언어는 a, 원저작 언어는 h에 기술한다. 원저작 언어를 모르면 h를 만들지 않는다. und를 자동으로 넣지 않는다. source는 ai_inference, review_required는 true다.

## Skip Rule

번역·다국어 정황이 없으면 041을 만들지 않는다. 본문언어 a 하나만 기술한 041은 008/35-37에 이미 있는 정보라서 추가 가치가 없으므로 만들지 않는다. 검증 단계에서도 a만 있고 번역 신호가 없으면 제거하고 '번역·다국어 근거 없음: 041 생성 보류'를 남긴다. 언어명은 있으나 3자리 부호를 확정할 수 없으면 만들지 않는다.

## Risk and Validation

언어부호는 소문자 3자리여야 한다. indicator2가 7이면 2 식별기호가 필수다. source가 ai_inference면 evidence가 필수다. 041과 546은 서로 일관되어야 한다.

## Retrieval Hints

- 041 정의
- 언어부호
- 번역물
- 041 지시기호
- 번역물 표시
- 부호 정보원
- 041 식별기호
- 원저작 언어 h
- 중역 k
- 041 생성
- 번역 정황
- 원어 확정
- 041 skipped
- 단일 언어
- 근거 부족
- 041 검증
- 546 일관성
