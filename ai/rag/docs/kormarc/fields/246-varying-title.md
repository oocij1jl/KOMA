# 246 여러 형태의 표제

## Metadata

- `chunk_group`: `kormarc.field.246`
- `tag`: `246`
- `field_name`: `여러 형태의 표제`
- `field_priority`: `conditional`
- `generation_path`: `llm` (evidence·biblio 기반 LLM 판단)
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/20X_24X_246.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-09-24`

## Purpose

246은 자료에 나타나는 다른 형태의 표제를 기술하는 반복 필드다. 대등표제, 원표제, 표지표제, 약칭 등 245 본표제와 실제로 다른 표제가 있을 때만 쓴다.

## Service Generation Rule

evidence나 biblio에서 245 본표제와 다른 표제가 명시적으로 확인될 때만 만든다. 245에 이미 ▼x 대등표제로 기술했다면 중복해서 만들지 않는다.

## Skip Rule

245 본표제와 같은 값을 246으로 만들지 않는다. '변형 표제 가능성'처럼 추정만으로 만들지 않는다. 확인된 다른 표제가 없으면 '대체표제 근거 없음'으로 남긴다.

## Retrieval Hints

- 246 정의
- 변형표제
- 원표제
- 246 생성
- 대등표제
- 원표제
- 246 skipped
- 동일 표제 금지
- 가능성 금지
