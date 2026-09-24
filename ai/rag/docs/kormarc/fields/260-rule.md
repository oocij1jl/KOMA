# 260 발행, 배포, 간사사항

## Metadata

- `chunk_group`: `kormarc.field.260`
- `tag`: `260`
- `field_name`: `발행, 배포, 간사사항`
- `generation_path`: `rule` (코드가 biblio에서 결정론적으로 생성한다. LLM 생성 대상 아님)
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/250_28X_260.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-09-24`

## 생성 주체

260은 `backend/services/deterministic_fields.py`가 만든다. LLM 프롬프트의 생성 대상에서 제외되며, LLM이 이 태그를 출력해도 무시된다.

## Purpose

260은 발행·배포·간사 사항을 기술하는 해당시필수 필드다. 이 서비스에서는 biblio.publisher와 biblio.publish_year를 코드가 전사한다.

## Indicators

제1지시기호는 발행사항의 순차이며 단행본 최초 발행은 공백이다. 제2지시기호는 미정의라 공백이다.

## Subfields

허용 식별기호는 a 발행지, b 발행처, c 발행년, e 제작지, f 제작처, g 제작년, 3, 6, 8이다. 이 서비스는 b와 c만 생성한다.

## Service Generation Rule

biblio.publisher를 b에, biblio.publish_year를 c에 기술한다. 발행지(a)는 국중도와 정보나루 모두 제공하지 않으므로 생성하지 않고 검수에 맡긴다. 출판사 주소나 서울 같은 기본값을 추정해 넣지 않는다. publish_predate는 출판예정일이므로 발행년으로 단정하지 않는다.

## Forbidden

발행지를 추정해 넣지 않는다. 발행년을 추정하지 않는다. 출판사명을 임의로 줄이거나 바꾸지 않는다.

## Retrieval Hints

- 260 정의
- 발행사항
- 260 지시기호
- 발행사항 순차
- 260 식별기호
- 발행지 a
- 발행처 b
- 발행년 c
- 260 생성
- 발행지 미수집
- 발행예정일
- 260 금지
- 발행지 추정 금지
