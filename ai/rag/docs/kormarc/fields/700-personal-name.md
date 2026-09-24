# 700 부출표목 - 개인명

## Metadata

- `chunk_group`: `kormarc.field.700`
- `tag`: `700`
- `field_name`: `부출표목 - 개인명`
- `field_priority`: `required`
- `generation_path`: `llm` (evidence·biblio 기반 LLM 판단)
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/70X_75X_700.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-09-24`

## Purpose

700은 부출표목의 표목이 개인명인 해당시필수 반복 필드다. 이 서비스는 1XX 기본표목을 만들지 않고 저자를 700으로 부출한다. 근거는 biblio.author 문자열 하나뿐이므로 인명 분해는 검수 대상이다.

## Indicators

제1지시기호는 개인명 유형으로 0 성으로 시작하지 않는 이름, 1 성으로 시작하는 이름, 3 가계명이다. 한글 인명은 성으로 시작하므로 통상 1이다. 제2지시기호는 부출표목 유형으로 공백은 해당정보 없음, 2는 분출표목이다. 분출 근거가 없으면 공백을 쓴다.

## Subfields

이 서비스가 쓰는 식별기호는 a 개인명(반복불가)과 e 역할어다. d 생몰년, c 이름 관련 정보, q 이름의 완전형, t 저작의 표제는 전거 근거가 있을 때만 쓴다. 전거 확인 없이 생몰년을 만들지 않는다.

## Service Generation Rule

biblio.author에서 식별되는 개인마다 700을 하나씩 만든다. 이름만 a에 넣고 역할어는 e에 분리해 넣는다. 지음·글·그림·옮김·엮음 같은 역할 표기를 이름에 붙여 두지 않는다. 한 필드에 여러 사람을 묶지 않는다. 245 책임표시와 인원이 일치해야 한다.

## Skip Rule

biblio.author가 비어 있으면 700을 만들지 않는다. 이름 경계를 확정할 수 없으면 추측해서 쪼개지 말고 생성을 보류하고 사유를 남긴다. 단체명은 700이 아니라 710이다.

## Forbidden

전거 근거 없이 생몰년·한자명·소속을 만들지 않는다. 기본표목 100을 만들지 않는다. 저작에 없는 사람을 추가하지 않는다. 출판사명이나 총서명을 인명으로 넣지 않는다.

## Retrieval Hints

- 700 정의
- 개인명 부출
- 저자 접근점
- 700 지시기호
- 개인명 유형
- 분출표목
- 700 식별기호
- 역할어 e
- 생몰년 d
- 700 생성
- 역자
- 그림작가
- 공저
- 700 skipped
- 저자 없음
- 단체명
- 700 금지
- 생몰년 금지
- 100 금지
