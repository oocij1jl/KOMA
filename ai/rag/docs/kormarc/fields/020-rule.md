# 020 국제표준도서번호

## Metadata

- `chunk_group`: `kormarc.field.020`
- `tag`: `020`
- `field_name`: `국제표준도서번호`
- `generation_path`: `rule` (코드가 biblio에서 결정론적으로 생성한다. LLM 생성 대상 아님)
- `source_type`: `official_kormarc_summary`
- `official_source`: https://librarian.nl.go.kr/kormarc/KSX6006-0/sub/01X_09X_020.html
- `schema_source`: `backend/docs/KOMA_스키마_v2.1.md`
- `last_reviewed`: `2026-09-24`

## 생성 주체

020은 `backend/services/deterministic_fields.py`가 만든다. LLM 프롬프트의 생성 대상에서 제외되며, LLM이 이 태그를 출력해도 무시된다.

## Purpose

020은 단행자료의 ISBN을 기술하는 반복 필드다. 이 서비스에서 020은 추론 필드가 아니라 biblio.isbn_ea, isbn_add_code, price, set_isbn을 코드가 그대로 옮기는 규칙 생성 필드다.

## Indicators

제1지시기호는 번호 구분이며 공백은 낱권 번호, 1은 세트 번호다. 제2지시기호는 미정의라 항상 공백이다. 낱권 ISBN과 세트 ISBN은 지시기호가 다르므로 020 필드를 나눠 기술한다.

## Subfields

허용 식별기호는 a 국제표준도서번호, c 입수조건, g 부가기호, q 부가적 식별정보, z 취소 ISBN, 6, 8이다. g 부가기호는 우리나라 ISBN에만 쓰는 5자리 숫자이므로 5자리 숫자가 아니면 기술하지 않는다. 가격은 c에 기술한다.

## Service Generation Rule

biblio.isbn_ea를 a에 기술한다. isbn_add_code가 5자리 숫자면 g에, price가 있으면 c에 기술한다. set_isbn이 있으면 제1지시기호 1로 별도 020을 만들고 set_expression은 q, set_add_code는 g에 기술한다. ISBN이 없으면 020을 만들지 않는다.

## Forbidden

ISBN을 계산하거나 추정해서 만들지 않는다. 부가기호 형식이 맞지 않으면 버리고 임의로 채우지 않는다. 가격을 추정하지 않는다.

## Retrieval Hints

- 020 정의
- ISBN
- 부가기호
- 020 지시기호
- 세트 번호
- 020 식별기호
- 부가기호 g
- 입수조건 c
- 020 생성
- 세트 ISBN
- 가격
- 020 금지
- ISBN 생성 금지
