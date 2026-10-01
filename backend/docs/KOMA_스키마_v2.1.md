# KOMA 데이터 스키마 (동결본 v2.1)

> 상태: **FROZEN (동결)** — 변경 시 버전 올림 + 이력 기록 필수
> 목적: 백엔드(API 조회) ↔ AI(LLM 생성) ↔ 프론트(검수/내보내기) ↔ 팀원 A(RAG 규칙) 간 **계약(contract)**
> 원칙: ① 근거 없는 값 임의 생성 금지(추론은 허용, 단 근거+출처+검수 필수) ② KORMARC(KS X 6006-0) 준수 ③ 검수 가능한 초안

## 변경 이력
| 버전 | 변경 내용 |
|---|---|
| v0.1 | 초안 |
| v1.0 | ① 구두점 후처리 ② 부제 LLM 분리 ③ 변환 함수 1개·텍스트 우선 ④ raw 로컬저장 / `₩`는 값·`:`는 후처리 |
| v1.1 | 차별점: evidence 블록 분리 / field_evidence_map / 정보나루 API 4개 / (C)에 evidence / 추론 필드 확정 |
| v2.0 | ① (C)에 `display` 필드 ② 저장은 순수 값 ③ available=false→skipped ④ field_evidence_map 확정 |
| **v2.1** | **주제 색인 재설계**: 차별점 주력을 **650→653(비통제 색인어)**로 변경. 650은 보조(통제 주제명, 제2지시기호 출처 미확정 시 생성 금지). 실무 .mrc 33권이 전부 653 사용·정보나루 키워드=비통제 자유어라는 근거 반영 |

## 표시 vs 저장 원칙 (v2.0 핵심)
- **저장(value)**: 순수 값. 구두점·▼기호 없음. (검증·수정·재사용 위해)
- **표시(display)**: 백엔드가 ISBD 구두점을 조립한 완성형 문자열을 (C)에 함께 제공. 검수 화면은 이걸 그대로 출력.
- 조립 규칙(KORMARC 구두점)은 **백엔드 한 곳**(`json_to_marc`와 공유)에 정의. 프론트는 KORMARC를 몰라도 됨.

## 차별점 요약 (왜 v1.1인가)
LAS/국중도 MARC 가져오기와의 차별점은 **API에 답이 없는 필드를 근거와 함께 AI가 제안**하는 것이다.
- **가져오기 필드** (020/245/260/700): biblio 사용. 차별점 아님.
- **추론 필드** (653/650/056/082/546/041/500): evidence(정보나루 키워드·책소개·함께대출도서) 기반 추론. **여기가 차별점.**
  - **653(비통제 색인어) = 주력.** 정보나루 키워드(자유어)를 근거로 생성. 제2지시기호 없음 → 임의 생성 위험 낮음.
  - **650(통제 주제명) = 보조.** 표목표 출처(제2지시기호)를 확정할 수 없으면 생성하지 않음.
- 추론도 "임의 생성"이 아니다: 근거 데이터 존재 + source=ai_inference + review_required=true 3조건 충족.

## 주제 색인 정책 (v2.1 핵심) — 653 주력 / 650 보조

근거: 실무 .mrc 33권이 **전부 653만 사용(650 0건)**, 정보나루 키워드는 **비통제 자유어**이므로 통제어 필드(650)에 직접 넣으면 왜곡.

| | 653 비통제 색인어 (주력) | 650 통제 주제명 (보조) |
|---|---|---|
| 통제 여부 | 비통제(자유 키워드) | 통제(주제명표목표에서 선택) |
| 제2지시기호 | **없음(빈칸)** | **주제명표목표 출처 코드 필요** |
| 값 | 정보나루 키워드 최소 정제 | 표목표에 맞게 정제 |
| 생성 조건 | 키워드 있으면 생성 | **출처(제2지시기호) 확정 가능할 때만** |
| 미충족 시 | — | **skipped** ("통제 주제명은 표목표 대조 필요") |

**규칙**
- 정보나루 키워드 → **기본 653로 생성**. ▼a에 키워드 하나씩(가중치 상위 N개 선별), 제2지시기호 빈칸, 명사형 최소 정제(조사 제거 등).
- 650은 **표목표 출처를 알 수 없으면 제2지시기호를 채우지 않으며, 함부로 승격하지 않는다.** 확실할 때만 제안 + review_required=true. 애매하면 653만 두고 650은 skipped.
- 제2지시기호(주제명표목표 출처 코드)는 **LLM이 임의로 지정 금지** — 근거 없는 코드 부여는 임의 생성 위반. (표목표 출처 코드 판단은 RAG ②층 가이드 대상)

---

## 0. 전체 데이터 흐름

```
[국중도 SearchApi]      ─┐
[정보나루 srchDtlList]   ─┼─→ (A) biblio   ─┐
[정보나루 keywordList]   ─┼─→ (A') evidence ─┼─→ (B) LLM입력 ─→ [LLM] ─→ (C) 구조화JSON ─→ [검수UI] ─→ (C') 검수본
[정보나루 usageAnalysis] ─┘                  │                                                          │
                                             field_evidence_map                       [json_to_marc()] ─→ .mrk
```

- **가져오기 경로**: biblio → 020/245/260/700
- **추론 경로**: evidence + field_evidence_map → 653/650/056/082/546/041/500 (차별점)

| 스키마 | 생성 주체 | 사용 주체 |
|---|---|---|
| (A) biblio | 백엔드 `lookup.py` | AI(가져오기 필드), 프론트(원문 표시) |
| (A') evidence | 백엔드 `lookup.py` | AI(추론 필드 근거) |
| (B) LLM 입력 | `generate.py` 조립 | LLM |
| (C) 구조화 JSON | LLM | 프론트(검수), `validate.py` |
| (C') 검수본 JSON | 프론트(사용자 수정) | `json_to_marc()` — **(C)와 동일 구조** |

### 정보나루 API 역할 분담 (중복 제거)
| API | 취하는 데이터 | 버리는 데이터 |
|---|---|---|
| `srchDtlList` | KDC(class_no), **description(책소개)** | — |
| `keywordList` | **키워드 50건 + 가중치** (주 소스) | 중복 서지정보 |
| `usageAnalysisList` | **co_loan_books(함께 대출된 도서)만** | 중복 키워드·description |

> 호출 실패 처리: evidence API(키워드·이용분석) 실패해도 가져오기 필드(020/245/260)는 정상 생성. 해당 추론 필드만 skipped 처리(graceful degradation).

---

## 1. 핵심 설계 규칙 (값 vs 표현 분리)

이 프로젝트의 가장 중요한 원칙. **저장(JSON)에는 순수 값만, 표현(구두점)은 변환 시 조립.**

### 1-A. 값 생성 단계(LLM/백엔드)에서 정규화 — 후처리로 미루지 않음
값 자체의 형식 규칙. 검증·비교·재사용을 위해 저장 시점에 확정한다.
- ISBN: 하이픈 제거, 숫자만 (`9791194160004`)
- 출판연도: 4자리 숫자 (`2024`)
- 가격: 콤마 제거. **`₩` 기호는 값에 포함** (`₩17000`) ← .mrc 실사례·표준 예시 일치
- 지시기호 값: 0/1 등 판단된 값

### 1-B. 후처리(`json_to_marc`)에서 조립 — JSON 값에 넣지 않음
ISBD 구두점 등 "값과 값 사이를 잇는 표시 기호".
- 식별기호 앞 구두점: ▼c 앞 ` :`, 책임표시(▼d) 앞 ` /`, 부제(▼b) 앞 ` :`, 권차 앞 ` ;` 등
- 필드 종단 구두점
- **예) 020**: JSON엔 `▼g="03100"`, `▼c="₩17000"` → 변환 시 `▼g03100 :▼c₩17000`
  - ▼c가 없으면 ` :`도 붙지 않음 (조건부 구두점은 변환기가 판단)

> `₩`는 입수조건(가격)의 일부라 값에 포함, ` :`는 ▼g↔▼c 구분자라 후처리. **이 둘의 경계가 동결 기준.**

---

## 2. 공통 enum

```jsonc
// source: 값의 출처 (IA 출처유형 표와 일치)
"api" | "user_input" | "ai_generated" | "ai_inference" | "user_edited"

// confidence: 생성 신뢰도
"high" | "medium" | "low"

// field_priority: 생성 정책
"required"        // 020, 245, 260, 700/710
"review_required" // 056, 082, 650
"conditional"     // 041, 246, 250, 300, 490, 500, 546, 830, 950
```

- 모든 `tag`: 문자열 3자리. `indicator1/2`: 문자열 1자리. **공백 지시기호는 `" "`(공백 1칸).**

---

## 3. (A) biblio 스키마 — 백엔드 조회 결과

`merge_biblio()` 반환 객체. API 응답 필드명은 두 매뉴얼 원문 기준 확정.
**응답은 `biblio`와 `raw`를 분리** (4번 결정: raw는 기본 화면 비표시, 로컬 저장 후 요청 시 조회).

```jsonc
{
  "found": true,
  "isbn": "9791194160004",

  // === 020 입수사항 근거 ===
  "isbn_ea": "9791194160004",     // 국중도 EA_ISBN / 정보나루 isbn13
  "isbn_add_code": "03100",       // EA_ADD_CODE / addition_symbol → 020 ▼g (값만, ' :'는 후처리)
  "set_isbn": "",                 // SET_ISBN → 020(세트, 지시기호1='1')
  "set_add_code": "",             // SET_ADD_CODE
  "set_expression": "",           // SET_EXPRESSION ("세트","전2권")
  "price": "",                    // PRE_PRICE → 020 ▼c(입수조건). 값은 '₩'+숫자, 콤마 제외

  // === 245 표제와 책임표시사항 근거 ===
  "title": "다윈 진화론 이데올로기에 맞짱을!",  // TITLE / bookname → 245 ▼a
  "author": "박홍순 지음",         // AUTHOR / authors → 245 ▼d, 700
  "volume": "",                   // VOL / vol → 245 ▼n
  // 부제(subtitle)는 biblio에 별도 키 없음 — title에 포함됨.
  // 분리는 LLM이 (C) 단계에서 수행 (2번 결정). 아래 4-부제규칙 참조.

  // === 260 발행·배포·간사사항 근거 ===
  "pub_place": "",                // ⚠ 두 API 미제공 → 260 ▼a 검수 필요
  "publisher": "숨쉬는책공장",     // PUBLISHER / publisher → 260 ▼b
  "publish_year": "2024",         // 정보나루 publication_year 우선 → 260 ▼c
  "publish_predate": "",          // 국중도 PUBLISH_PREDATE(출판예정일) 원본, 검수 참고용

  // === 분류 (검수 필수) ===
  "kdc": "470.12",                // KDC / class_no → 056 ▼a
  "kdc_edition": "",              // ⚠ 판차 미제공 → 056 ▼2 검수 필요 (임의 가정 금지)
  "kdc_name": "",                 // class_nm — 검수 보조용, MARC 비대상
  "ddc": "",                      // 국중도 DDC → 082 ▼a (정보나루 미제공)
  "ddc_edition": "",              // ⚠ 판차 미제공 → 082 ▼2 검수 필요
  "subject": "",                  // SUBJECT → 653(주력)/650(보조) 주제 색인 (검수 필수)

  // === 조건부 ===
  "edition_stmt": "",             // EDITION_STMT → 250
  "series_title": "",             // SERIES_TITLE → 490/830
  "series_no": "",                // SERIES_NO → 490 ▼v
  "page": "",                     // PAGE → 300 ▼a (명확할 때만)
  "book_size": "",                // BOOK_SIZE → 300 ▼c (세로 cm, 명확할 때만)
  "form": "종이책",                // FORM → 007/008
  "ebook_yn": "N",                // EBOOK_YN
  "description": "",              // 정보나루 description → 500(조건부) + evidence 원천(추론용)

  // === 임의생성 금지·표시 전용 ===
  "control_no": "",               // CONTROL_NO (CIP 제어번호) — ⚠ MARC 생성 금지, 표시만

  // === UI 표시 전용 (MARC 비대상) ===
  "cover_url": "",                // TITLE_URL / bookImageURL
  "toc_url": "",                  // BOOK_TB_CNT_URL
  "intro_url": "",                // BOOK_INTRODUCTION_URL

  // === 필드별 출처 추적 ===
  "field_sources": {
    "title": "nl.go.kr",
    "kdc": "data4library.kr",
    "price": "nl.go.kr"
  }
}
```

### raw 분리 (4번 결정)
- `/api/lookup/isbn` 응답: `{ "isbn": "...", "biblio": {...}, "raw": { "nl": {...}, "d4l": {...} } }`
- **프론트는 `biblio`만 기본 렌더링**, `raw`는 로컬 저장 후 "원문 보기" 시 로컬에서 표시.
- 별도 서버 재호출 없음 (이력 로컬 저장 구조와 일관).

### 빈 값 처리
- 없는 값은 **빈 문자열 `""`** (null 아님). 빈 값 = "근거 없음" → LLM이 `skipped` 처리.

---

## 3'. (A') evidence 스키마 — 추론 필드용 원재료 [v1.1 신규]

biblio가 "그대로 쓰는 확정값"이라면, evidence는 "AI가 읽고 해석할 원재료"다. **역할을 분리**하여 LLM이 키워드를 표제(245)에 잘못 넣는 등의 오염을 방지한다.

```jsonc
{
  "keywords": [                    // 정보나루 keywordList (가중치 내림차순)
    { "word": "진화론", "weight": 0.92 },
    { "word": "생물학", "weight": 0.81 },
    { "word": "철학",   "weight": 0.77 }
    // 최대 50건
  ],
  "description": "이 책은 다윈 진화론을 인문학적 시선에서...",  // srchDtlList description
  "co_loan_books": [               // usageAnalysisList coLoanBooks (함께 대출된 도서, 주제 맥락)
    { "bookname": "이기적 유전자", "isbn13": "...", "authors": "리처드 도킨스" }
    // 최대 10건
  ],
  // 추론 보조용 (biblio에서 복사)
  "title": "다윈 진화론 이데올로기에 맞짱을!",
  "author": "박홍순 지음",
  "kdc_from_api": "470.12",        // biblio.kdc (있으면 056 검수, 없으면 추론)
  "ddc_from_api": "",              // biblio.ddc

  // 번역서 감지 신호 (LLM이 채우는 게 아니라, 백엔드가 1차 탐지해 힌트로 제공)
  "translation_signals": {
    "detected": false,             // description/author에 '옮김·번역·translated' 또는 원저자 패턴
    "hints": []                    // 예: ["author에 '옮김' 포함", "원저자명 추정: ..."]
  },

  "available": {                   // 어떤 evidence가 실제로 수집됐는지 (호출 성공 여부)
    "keywords": true,
    "description": true,
    "co_loan_books": false         // API 실패/데이터 없음 → 해당 추론 시 참고 불가
  }
}
```

### evidence 처리 원칙
- evidence는 **추론 필드(653/650/056/082/546/041/500)에만** 사용. 가져오기 필드는 biblio만 사용.
- **[v2.0 확정] `available`이 false인 재료에만 의존하는 필드는 "근거 부족"으로 생성 실패** → `skipped_fields`에 `reason: "근거 부족 (필요 evidence 미수집: <재료명>)"`으로 남긴다. 절대 빈 값이나 추측으로 채우지 않는다.
- 일부 재료만 available한 경우: 가용 재료만으로 추론 가능하면 생성(confidence 하향), 불가하면 skipped. 판단 기준은 field_evidence_map 우선순위.
- evidence가 전부 비면(키워드·책소개·co_loan 모두 false) → 추론 필드 전부 skipped. **임의 생성 절대 금지.**
- `translation_signals`는 백엔드가 1차 탐지(정규식/키워드)해 힌트만 제공. 최종 판단은 LLM이 description 읽고 확정. (translation_signals도 evidence이므로 available 규칙 동일 적용)

### evidence 응답 분리
- `/api/lookup/isbn` 응답: `{ "isbn", "biblio", "evidence", "raw" }`
- 프론트 기본 렌더링: `biblio`. `evidence`는 검수 화면 "근거 보기"에서 사용. `raw`는 로컬 저장 후 "원문 보기".

---

## 4. (B) LLM 입력 스키마

```jsonc
{
  "biblio":   { /* (A) biblio, raw·url 제외 가능 */ },
  "evidence": { /* (A') evidence — 추론 필드용 원재료 */ },

  "generate_options": {
    "required_fields":        ["020", "245", "260", "700"],
    "review_required_fields": ["653", "650", "056", "082"],
    "conditional_fields":     ["041","246","250","300","490","500","546","830","950"],
    "allow_inference": true,    // v1.1: 추론 허용. 단 evidence 근거 있을 때만. 근거 없으면 skipped.
    "show_source": true,

    // [v1.1] 필드별 evidence 매핑 — "이 재료를 근거로 이 필드를 만들어라"
    "field_evidence_map": {
      "653": ["keywords", "description", "co_loan_books"],  // 비통제 색인어 (주력)
      "650": ["keywords", "description", "co_loan_books"],  // 통제 주제명 (보조, 출처확정 시만)
      "056": ["keywords", "kdc_from_api", "description"],   // KDC (없으면 추론)
      "082": ["keywords", "ddc_from_api", "description"],   // DDC
      "546": ["description", "title", "author"],            // 언어 (번역서)
      "041": ["translation_signals", "description", "author"], // 언어부호
      "500": ["translation_signals", "description", "author"]  // 원저자 주기 등
    }
  },

  "kormarc_rules": [   // RAG 검색 결과 주입 슬롯 
    {
      "tag": "020",
      "field_name": "국제표준도서번호",
      "rule": "", "indicators": "", "subfields": "",
      "examples": [], "forbidden": []
    }
  ],

  "constraints": [
    "근거 없는 값은 임의 생성하지 않는다. 정보가 없으면 skipped_fields에 사유와 함께 남긴다.",
    "ISBN은 하이픈 제거, 숫자만.",
    "출판연도는 4자리 숫자.",
    "가격(▼c)은 '₩'+숫자, 콤마 제외. 값에 ₩ 포함. (식별기호 사이 구두점 ' :'는 출력하지 말 것 — 후처리에서 조립)",
    "구두점(' :', ' /', ' ;', 종단 '.')은 값에 넣지 않는다. 값과 값 사이 표시 기호는 후처리가 담당.",
    "020 세트 ISBN은 제1지시기호 '1'.",
    "056/082는 분류값(▼a)+판차(▼2)를 함께. 판차 미확인 시 ▼2는 빈값 + review_required=true.",
    "크기는 세로 cm, 임의 생성 금지.",
    "제어번호·전거번호·청구기호는 임의 생성 금지.",
    "저자명은 100이 아닌 700에 부출(KORMARC 서명주기입).",
    "245 관제/관사는 MARC21 글자수 방식 금지, KORMARC(관제 연계) 규칙.",
    "700 제1지시기호: 성 시작=1, 이름 시작=0. 한글 인명 통상 1(검수 필요).",
    "태그 3자리, 지시기호 2자리. 공백 지시기호는 ' '.",
    // --- 부제 분리 (2번 결정) ---
    "245 부제 분리: title에 ' : '(또는 명확한 부제 구분자)가 있을 때만 ▼a(본표제)/▼b(부제)로 나눈다. 구분자가 없으면 분리하지 말고 전체를 ▼a에 두고 note에 '부제 미확인'을 남긴다. 근거 없는 임의 분리 금지.",
    // --- [v1.1] 추론 필드 공통 ---
    "추론 필드(653/650/056/082/546/041/500)는 field_evidence_map이 지정한 evidence만 근거로 사용한다. 지정된 evidence가 모두 비어 있으면(available=false) 해당 필드를 생성하지 말고 skipped_fields에 남긴다.",
    "추론으로 만든 필드는 source='ai_inference', review_required=true, 그리고 evidence 객체(어떤 근거를 썼는지)를 반드시 포함한다. 근거 없는 추론 금지.",
    // --- [v2.1] 653 비통제 색인어 (주력) / 650 통제 주제명 (보조) ---
    "653 비통제 색인어: 정보나루 keywords(가중치 상위)를 근거로 생성한다. ▼a에 키워드를 하나씩 기술하고(상위 N개 선별), 제2지시기호는 빈칸(비통제어라 출처 없음). 조사 제거 등 명사형 최소 정제만 하고 의미를 바꾸지 않는다. co_loan_books·description은 키워드 보조. 각 653의 evidence.keywords_used에 사용 키워드를 기록한다.",
    "650 통제 주제명: 주제명표목표 출처를 확정할 수 있을 때만 생성한다. 출처를 모르면 제2지시기호를 임의로 채우지 말고 650을 skipped 처리한다(reason: '통제 주제명은 표목표 대조 필요'). 정보나루 키워드(자유어)를 근거 없이 650으로 승격하지 않는다. 생성 시 review_required=true, confidence는 low~medium.",
    // --- [v1.1] 056/082 분류 ---
    "056/082: kdc_from_api/ddc_from_api가 있으면 그 값을 채우고(판차 검수), 없으면 keywords·description 기반으로 분류 후보를 추론한다. 추론 시 confidence='low'. 분류는 정확도가 낮으므로 항상 review_required=true.",
    // --- [v1.1] 번역서 처리 546/041/500 ---
    "번역서 처리: translation_signals.detected가 true이거나 description/author에서 번역 정황(옮김·번역·translated·원저자명)이 확인될 때만 546(언어)·041(언어부호)·500(원저자 주기)을 제안한다. 정황이 없으면 세 필드 모두 skipped. 추정 원저자명은 임의 생성 금지 — description에 실제로 나타난 경우만 사용."
  ]
}
```

---

## 5. (C) 구조화 JSON 스키마 — LLM 출력 / 검수본 공통

> LLM은 MARC 텍스트를 직접 출력하지 않는다. 아래 구조만 출력.
> **검수본(C')도 동일 구조** — 사용자가 값 수정 시 해당 필드 `source`를 `user_edited`로 변경. (3번 결정)

```jsonc
{
  "fields": [
    {
      "tag": "020",
      "indicator1": " ",
      "indicator2": " ",
      "subfields": [                              // 순서 보존 = MARC 출력 순서. value는 순수 값.
        { "code": "a", "value": "9791194160004", "prefix": "" },
        { "code": "g", "value": "03100",         "prefix": "" },
        { "code": "c", "value": "₩17000",        "prefix": " :" }  // ▼c 앞 ISBD 구두점
      ],
      "display": "▼a9791194160004▼g03100 :▼c₩17000",  // [v2.0] 백엔드 조립 표시용
      "source": "api",
      "review_required": false,
      "confidence": "high",
      "note": ""
    },
    {
      "tag": "245",
      "indicator1": "1",
      "indicator2": "0",
      "subfields": [
        { "code": "a", "value": "다윈 진화론 이데올로기에 맞짱을!", "prefix": "" },
        { "code": "b", "value": "인문학의 시선에서 통찰한 과학",     "prefix": " :" },  // 부제 앞
        { "code": "d", "value": "박홍순 지음",                       "prefix": " /" }   // 책임표시 앞
      ],
      "display": "▼a다윈 진화론 이데올로기에 맞짱을! :▼b인문학의 시선에서 통찰한 과학 /▼d박홍순 지음",
      "source": "ai_generated",
      "review_required": false,
      "confidence": "medium",
      "note": "title 내 ' : ' 기준 부제 분리. 제1지시기호=표제부출(1), 제2=관제없음(0)"
    },
    {
      "tag": "056",
      "indicator1": " ",
      "indicator2": " ",
      "subfields": [
        { "code": "a", "value": "470.12" },
        { "code": "2", "value": "" }              // 판차 미확인
      ],
      "source": "api",
      "review_required": true,
      "confidence": "low",
      "note": "KDC값 API 제공, 판차(▼2) 미확인 — 검수 필요"
    },
    {
      // [v2.1] 추론 필드 주력 예시 — 653 비통제 색인어 (정보나루 키워드 기반)
      "tag": "653",
      "indicator1": " ",
      "indicator2": " ",
      "subfields": [
        { "code": "a", "value": "진화론", "prefix": "" },
        { "code": "a", "value": "생물학", "prefix": "" },
        { "code": "a", "value": "철학",   "prefix": "" }
      ],
      "display": "▼a진화론▼a생물학▼a철학",
      "source": "ai_inference",
      "review_required": true,
      "confidence": "medium",
      "note": "정보나루 키워드 기반 비통제 색인어 — 검수 필요",
      "evidence": {
        "from": ["keywords"],
        "keywords_used": ["진화론(0.92)", "생물학(0.81)", "철학(0.77)"],
        "reasoning": "가중치 상위 키워드를 명사형으로 최소 정제. 비통제어라 제2지시기호 빈칸"
      }
    },
    {
      // [v1.1] 번역서 처리 예시 — 정황 있을 때만
      "tag": "546",
      "indicator1": " ",
      "indicator2": " ",
      "subfields": [
        { "code": "a", "value": "영어 원작을 한국어로 번역", "prefix": "" }
      ],
      "display": "▼a영어 원작을 한국어로 번역",
      "source": "ai_inference",
      "review_required": true,
      "confidence": "medium",
      "note": "책소개에서 번역 정황 확인 — 검수 필요",
      "evidence": {
        "from": ["translation_signals", "description"],
        "reasoning": "author에 '옮김' 포함, description에 원저자명 언급"
      }
    }
  ],

  "skipped_fields": [
    { "tag": "650", "reason": "통제 주제명은 주제명표목표 대조 필요 — 출처(제2지시기호) 미확정. 653로 대체" },
    { "tag": "082", "reason": "DDC·키워드 근거 부족 — 임의 생성 금지" },
    { "tag": "300", "reason": "페이지수·크기 정보 없음 — 임의 생성 금지" },
    { "tag": "041", "reason": "번역 정황 없음 — 조건 미충족" }
  ],

  "warnings": [
    "260 발행지(▼a)는 두 API 모두 미제공 — 표제면 확인 필요",
    "653 색인어는 키워드 기반 추론 — 반드시 검수",
    "650 통제 주제명은 표목표 대조가 필요해 미생성 — 653로 대체함"
  ]
}
```

> **evidence 필드** (추론 필드에만 존재): `from`(사용한 evidence 종류), `keywords_used`(쓴 키워드), `reasoning`(제안 근거). 검수 화면 "근거 보기"에서 사서에게 표시. 가져오기 필드(020/245 등)에는 없음.

### [v2.0] display / prefix 규칙 — 표시 vs 저장 분리
- **`value`**: 순수 값. LLM이 생성하고 사용자가 수정하는 대상. 구두점·▼기호 없음.
- **`prefix`**: 해당 식별기호 **앞에 붙는 ISBD 구두점** (예: ▼c 앞 `" :"`, ▼d 앞 `" /"`). **백엔드가 채운다.** LLM은 생성하지 않음(빈 문자열로 두거나 생략).
- **`display`**: 필드 전체를 조립한 표시용 문자열. **백엔드가 `value`+`prefix`+▼기호로 조립.** 검수 화면이 그대로 출력.
- 책임 주체:
  - LLM(C 출력): `value`만 채움. `prefix`/`display`는 비움.
  - 백엔드: (C)를 받아 `prefix`/`display`를 채워 프론트에 전달. (검수본 C'도 수정 후 백엔드가 재조립)
  - 프론트: `display`를 읽기 전용으로 표시. 사용자가 값 편집 시엔 `value`만 수정 → 백엔드 재조립.
- **조립 규칙은 `json_to_marc()`와 동일 함수/테이블을 공유** (구두점 규칙이 두 곳에 흩어지지 않게).

### 필드 1건 불변식 (validate.py 검증)
- `tag`: `^\d{3}$`
- `indicator1`, `indicator2`: 길이 1 (공백 허용)
- `subfields`: ≥1개, 각 `code`는 영소문자/숫자 1자, `value`는 순수 값
- 필수필드 필수 식별기호: 245▼a, 020(▼a 또는 set_isbn), 260▼b
- `review_required=true` 또는 `confidence=low` → 검수 배지 강조
- **`value`에 ISBD 구두점 포함 금지** (검증으로 ' /', ' :' 등 trailing 구두점 경고). 구두점은 `prefix`/`display`에만.
- **`source="ai_inference"`인 필드는 `evidence` 객체 필수** (없으면 "근거 없는 추론"으로 간주 → 경고/차단)

---

## 6. MARC 변환 (3번 결정)

```
(C) 또는 (C') JSON ──→ json_to_marc(record) ──→ MARC 텍스트(.mrk)
```

- **변환 함수 1개**. 입력이 LLM 출력이든 검수본이든 동일 (C) 스키마라 분기 불필요.
- 변환 시 **구두점 조립**: 식별기호 순서대로 출력하되, 규칙에 따라 ▼ 앞에 ISBD 구두점 삽입.
  - 예: ▼g 다음 ▼c가 있으면 ▼g와 ▼c 사이에 ` :` / ▼d 앞 ` /` / ▼b 앞 ` :` 등
- **[v2.0] 검수 화면의 `display`와 동일한 조립 규칙을 사용**한다. 즉 `prefix`/`display`를 만드는 로직과 `.mrk`를 만드는 로직은 **같은 구두점 테이블**을 공유 (한 곳 수정 = 양쪽 반영).
- MVP는 **텍스트(.mrk) 우선** (검수·복사용). ISO 2709 바이너리(.mrc)는 실제 시스템 반입 단계로 후순위.
- 출력 위치: 백엔드 (검증·display 조립과 동일 위치, 관심사 일관).

---

## 7. 검증 규칙 기준 (validate.py / 팀원 A 공유)

| 항목 | 규칙 | 위반 시 |
|---|---|---|
| 태그 형식 | 3자리 숫자 | 저장 차단 |
| 지시기호 | 각 1자리(공백 가능) | 저장 차단 |
| 식별기호 code | 영소문자/숫자 1자 | 즉시 오류 |
| 필수 식별기호 | 245▼a, 020▼a/set, 260▼b | 경고/차단 |
| ISBN 형식 | 10 또는 13자리(하이픈 제거 후) | 입력 차단 |
| 필수 필드 누락 | required 미생성 | 검수 배너 |
| 검수필요 필드 | review_required 강조 | 배지 |
| 값 내 구두점 | trailing ' /', ' :', ' ;' 등 | 경고(후처리 영역 침범) |
| [v1.1] 추론필드 근거 | source=ai_inference면 evidence 객체 존재 | 경고/차단 |
| [v1.1] 분류 추론 | 056/082 추론 시 confidence=low + review_required | 강제 검수 |

> 팀원 A의 "위험 필드 표시 기준" = `confidence`/`review_required` 부여 규칙과 일치시킬 것.
> [v2.1] 팀원 A는 추론 필드의 RAG 규칙에 다음을 포함할 것:
> - **653(주력)**: 정보나루 키워드를 비통제 색인어로 정제하는 기준(최소 정제, 의미 보존)
> - **650(보조)**: 주제명표목표 출처 코드(제2지시기호) 판단 기준 — 출처 미확정 시 생성 금지 규칙
> - **056/082**: 키워드 기반 분류 추론 및 판차(▼2) 기준

---

## 8. 변경 관리
- 동결 후 변경은 버전 올림 + 변경 이력 기록.
- 키 이름 변경은 백엔드/AI/프론트/RAG **4곳 동시 영향** → 가급적 고정.
