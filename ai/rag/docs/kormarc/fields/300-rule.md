# 300 형태사항

## Metadata

- `chunk_group`: `kormarc.field.300`
- `tag`: `300`
- `field_name`: `형태사항`
- `generation_path`: `rule` (코드가 biblio에서 결정론적으로 생성한다. LLM 생성 대상 아님)
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/3XX_300.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-09-24`

## 생성 주체

300은 `backend/services/deterministic_fields.py`가 만든다. LLM 프롬프트의 생성 대상에서 제외되며, LLM이 이 태그를 출력해도 무시된다.

## Purpose

300은 수량, 기타 물리적 특성, 크기를 기술하는 필수 필드다. 이 서비스에서는 biblio.page와 biblio.book_size를 코드가 변환한다.

## Indicators

제1지시기호와 제2지시기호는 미정의이므로 항상 공백이다.

## Subfields

허용 식별기호는 a 특정자료종별과 수량, b 기타 물리적 특성, c 크기, e 딸림자료, f 단위 유형, g 단위 크기, 3, 6, 8이다. 크기는 일반적으로 cm 단위로 기술한다.

## Service Generation Rule

biblio.page에서 수량을 뽑아 a에 기술한다. API 문자열에 장·책·권·면·매 단위가 있으면 그 단위를 따르고 없으면 p.를 쓴다. biblio.book_size가 mm이면 큰 값을 세로로 보고 cm로 올림해 c에 기술하고, cm이면 그대로 쓴다.

**단위 표기가 아예 없는 경우**(예: `188*257`): 국중도/정보나루 API가 실제로 이 형태로 값을 준다(가로*세로, mm, 단위 생략 — 2026-09-25 실API 응답으로 확인). 숫자·구분자 외 다른 문자가 전혀 없고 최댓값이 100 이상이면 mm 관례를 적용해 c를 만든다. "22"처럼 이미 cm로 보이는 작은 값이나 인식 못 한 단위 문자가 섞인 값은 여전히 추정하지 않는다.

그 외에는 단위를 알 수 없으므로 크기를 만들지 않는다. 수량과 크기가 모두 없으면 300을 만들지 않고 '형태사항 근거 없음'을 남긴다.

## Forbidden

삽화·천연색삽화·초상 같은 기타 물리적 특성(b)은 근거가 없으므로 만들지 않는다. 쪽수나 크기를 추정하지 않는다. 0 p. 같은 무의미한 값을 남기지 않는다.

## Retrieval Hints

- 300 정의
- 형태사항
- 300 지시기호
- 300 식별기호
- 특정자료종별
- 삽화 b
- 크기 c
- 300 생성
- 페이지 변환
- 크기 cm 변환
- 300 금지
- 삽화 추정 금지
