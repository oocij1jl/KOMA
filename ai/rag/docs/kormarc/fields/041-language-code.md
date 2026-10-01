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

041의 각 언어와 역할은 evidence.available.description=true인 description에서 직접 확인한다. '한국어로 번역'은 a, '영어 원작'은 h, '영어 요약'은 b, '일본어 목차'는 f, 명시된 중역 언어는 k의 근거다. '한국어와 영어로 병기'처럼 명시된 다국어 본문도 허용한다. translation_signals는 available.translation_signals=true이고 detected=true일 때 번역 정황만 보조하며 언어 자체를 확정하지 않는다. 저자·역자 이름, 국적, 한국어 표제, LLM의 evidence.reasoning으로 원어를 추정하지 않는다. source는 ai_inference, review_required는 true다.

## Skip Rule

입력에서 확인되지 않는 언어 식별기호는 제거한다. 남은 언어가 없거나, 번역 정황 없이 단일 본문언어 a만 남으면 041을 보류한다. 서로 다른 본문언어 a가 둘 이상이거나 요약·목차·원저·중역 언어의 명시 근거가 있으면 유지한다. 원저작 언어를 모르면 h나 und를 임의로 채우지 않는다. unavailable 자료와 출력 자체의 주장으로 필드를 유지하지 않는다. 보류 사유는 '번역·다국어 근거 없음: 041 생성 보류'다.

## Risk and Validation

자동 검증의 언어명 대응은 한국어(kor), 영어(eng), 독일어(ger), 스페인어(spa), 일본어(jpn), 중국어(chi), 프랑스어(fre)와 역할이 명시된 소문자 3자리 입력 부호로 한정한다. 미지원 언어명·불명확한 역할·부정 또는 추정 표현은 추측하지 않고 보류한다. 이는 완전한 언어 판별기가 아닌 보수적인 서비스 정책이며 사서 검수가 필요하다. indicator2가 7이면 2 식별기호가 필수다. source가 ai_inference면 evidence가 필수다. 041과 546은 서로 일관되어야 한다.

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
