# 250 판사항

## Metadata

- `chunk_group`: `kormarc.field.250`
- `tag`: `250`
- `field_name`: `판사항`
- `generation_path`: `rule` (코드가 biblio에서 결정론적으로 생성한다. LLM 생성 대상 아님)
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/250_28X_250.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-09-24`

## 생성 주체

250은 `backend/services/deterministic_fields.py`가 만든다. LLM 프롬프트의 생성 대상에서 제외되며, LLM이 이 태그를 출력해도 무시된다.

## Purpose

250은 저작의 판과 관련된 정보를 기술하는 해당시필수 필드다. 이 서비스에서는 국중도 EDITION_STMT에서 온 biblio.edition_stmt가 있을 때만 코드가 전사한다.

## Indicators

제1지시기호와 제2지시기호는 모두 미정의이므로 항상 공백이다.

## Subfields

허용 식별기호는 a 판 표시, b 해당 판의 책임표시, 3, 6, 8이다. 판 표시는 반복불가다.

## Service Generation Rule

biblio.edition_stmt를 a에 그대로 기술한다. 판사항이 비어 있으면 250을 만들지 않고 skipped_fields에 '판사항 근거 없음: 판 표시 미수집'을 남긴다. 판 표시가 없다고 초판으로 가정하지 않는다.

## Retrieval Hints

- 250 정의
- 판사항
- 250 지시기호
- 250 식별기호
- 판 표시
- 250 생성
- 초판 가정 금지
