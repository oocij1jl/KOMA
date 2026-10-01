import json
import unittest

from backend.schemas.lookup import BiblioSchema, EvidenceSchema
from backend.services.output_validator import OutputValidationError, validate_output


class OutputValidatorTests(unittest.TestCase):
    def _build_biblio(self, **overrides: object) -> BiblioSchema:
        data: dict[str, object] = {
            "found": True,
            "isbn_ea": "9788936434120",
            "title": "채식주의자",
            "author": "한강 지음",
            "publisher": "창비",
            "series_title": "창비 장편소설",
            "field_sources": {},
        }
        data.update(overrides)
        return BiblioSchema.model_validate(data)

    def _build_evidence(self, **overrides: object) -> EvidenceSchema:
        data: dict[str, object] = {
            "keywords": [{"word": "채식주의", "weight": 0.91}],
            "description": "채식주의를 선택한 인물을 둘러싼 한국 장편소설.",
            "co_loan_books": [{"bookname": "소년이 온다", "isbn13": "9788936434267", "authors": "한강"}],
            "title": "채식주의자",
            "author": "한강 지음",
            "kdc_from_api": "813.7",
            "ddc_from_api": "895.735",
            "translation_signals": {"detected": False, "hints": []},
            "available": {
                "keywords": True,
                "description": True,
                "co_loan_books": True,
                "translation_signals": False,
            },
        }
        data.update(overrides)
        return EvidenceSchema.model_validate(data)

    def test_validate_output_removes_650_and_adds_skip_reason(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "650",
                        "indicator1": " ",
                        "indicator2": "8",
                        "subfields": [{"code": "a", "value": "한국 소설"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "low",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    },
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "채식주의"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {
                            "from": ["keywords"],
                            "keywords_used": ["채식주의(0.91)"],
                            "reasoning": "키워드 근거",
                        },
                    },
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual([field.tag for field in result.fields], ["653"])
        self.assertEqual(result.skipped_fields[0].tag, "650")
        self.assertEqual(result.skipped_fields[0].reason, "통제 주제명은 표목표 대조 필요: 653으로 대체")
        self.assertIn("650은 기본 skip", result.warnings[0])

    def test_validate_output_normalizes_structural_punctuation(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": " /채식주의:"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields[0].subfields[0].value, "채식주의")
        self.assertIn("653$a 값의 구두점을 제거했습니다.", result.warnings)

    def test_validate_output_rewrites_existing_650_skip_reason(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [],
                "skipped_fields": [{"tag": "650", "reason": "통제 주제명은 표목표 대조 필요"}],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields, [])
        self.assertEqual(result.skipped_fields[0].tag, "650")
        self.assertEqual(result.skipped_fields[0].reason, "통제 주제명은 표목표 대조 필요: 653으로 대체")

    def test_validate_output_normalizes_api_source_aliases(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "245",
                        "indicator1": "0",
                        "indicator2": "0",
                        "subfields": [{"code": "a", "value": "채식주의자"}],
                        "source": "d4l",
                        "review_required": False,
                        "confidence": "high",
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields[0].source, "api")

    def test_validate_output_recovers_missing_evidence_for_api_like_fields(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "245",
                        "indicator1": "0",
                        "indicator2": "0",
                        "subfields": [{"code": "a", "value": "채식주의자"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                    },
                    {
                        "tag": "500",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "근거 없는 주기"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                    },
                    {
                        "tag": "546",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                    },
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual([(field.tag, field.source) for field in result.fields], [("245", "api")])
        self.assertEqual([item.tag for item in result.skipped_fields], ["500", "546"])

    def test_validate_output_rejects_invalid_json(self) -> None:
        with self.assertRaises(OutputValidationError):
            _ = validate_output("not json")

    def test_validate_output_skips_missing_ai_evidence(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "채식주의"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields, [])
        self.assertEqual(result.skipped_fields[0].tag, "653")
        self.assertIn("evidence 누락", result.skipped_fields[0].reason)

    def test_validate_output_filters_653_terms_using_biblio_context(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [
                            {"code": "a", "value": "채식주의"},
                            {"code": "a", "value": "한강"},
                            {"code": "a", "value": "창비"},
                            {"code": "a", "value": "창비 장편소설 시리즈"},
                            {"code": "a", "value": "소년이 온다"},
                            {"code": "a", "value": "폭력"},
                        ],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(
            raw_output,
            biblio=self._build_biblio(),
            evidence=self._build_evidence(),
        )

        self.assertEqual([subfield.value for subfield in result.fields[0].subfields], ["채식주의", "폭력"])
        self.assertEqual(result.skipped_fields, [])

    def test_validate_output_filters_series_title_and_co_loan_title_contamination(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [
                            {"code": "a", "value": "원미동 사람들"},
                            {"code": "a", "value": "민음사 세계문학전집"},
                            {"code": "a", "value": "실존주의"},
                        ],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(
            raw_output,
            biblio=self._build_biblio(title="이방인", author="알베르 카뮈", publisher="민음사", series_title="세계문학전집"),
            evidence=self._build_evidence(
                title="이방인",
                author="알베르 카뮈",
                co_loan_books=[{"bookname": "원미동 사람들", "isbn13": "9780000000000", "authors": "양귀자"}],
            ),
        )

        self.assertEqual([subfield.value for subfield in result.fields[0].subfields], ["실존주의"])
        self.assertEqual(result.skipped_fields, [])

    def test_validate_output_skips_653_when_no_independent_terms_remain(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [
                            {"code": "a", "value": "채식주의자"},
                            {"code": "a", "value": "한강"},
                            {"code": "a", "value": "창비"},
                        ],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(
            raw_output,
            biblio=self._build_biblio(),
            evidence=self._build_evidence(),
        )

        self.assertEqual(result.fields, [])
        self.assertEqual(len(result.skipped_fields), 1)
        self.assertEqual(result.skipped_fields[0].tag, "653")
        self.assertEqual(result.skipped_fields[0].reason, "주제 색인어로 사용할 독립 근거 부족")

    def test_validate_output_rewrites_existing_653_skip_reason_when_context_removes_all_terms(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "한강 지음"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [{"tag": "653", "reason": "LLM 임시 이유"}],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(
            raw_output,
            biblio=self._build_biblio(),
            evidence=self._build_evidence(),
        )

        self.assertEqual(result.fields, [])
        self.assertEqual(len(result.skipped_fields), 1)
        self.assertEqual(result.skipped_fields[0].tag, "653")
        self.assertEqual(result.skipped_fields[0].reason, "주제 색인어로 사용할 독립 근거 부족")

    def test_validate_output_does_not_mark_653_skipped_when_another_653_survives(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "채식주의자"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    },
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "폭력"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    },
                ],
                "skipped_fields": [{"tag": "653", "reason": "기존 이유"}],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(
            raw_output,
            biblio=self._build_biblio(),
            evidence=self._build_evidence(),
        )

        self.assertEqual(len(result.fields), 1)
        self.assertEqual([subfield.value for subfield in result.fields[0].subfields], ["폭력"])
        self.assertEqual(result.skipped_fields, [])

    def test_validate_output_filters_co_loan_titles_even_when_evidence_is_unavailable(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "원미동 사람들"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["co_loan_books"], "reasoning": "공대출 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(
            raw_output,
            biblio=self._build_biblio(title="채식주의자", series_title="창비 장편소설"),
            evidence=self._build_evidence(
                co_loan_books=[{"bookname": "원미동 사람들 : 양귀자 소설", "isbn13": "9780000000000", "authors": "양귀자"}],
                available={
                    "keywords": True,
                    "description": True,
                    "co_loan_books": False,
                    "translation_signals": False,
                },
            ),
        )

        self.assertEqual(result.fields, [])
        self.assertEqual(result.skipped_fields[0].tag, "653")
        self.assertEqual(result.skipped_fields[0].reason, "주제 색인어로 사용할 독립 근거 부족")

    def test_validate_output_filters_publisher_series_contamination_by_containment(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [
                            {"code": "a", "value": "민음사 세계문학전집"},
                            {"code": "a", "value": "실존주의"},
                        ],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(
            raw_output,
            biblio=self._build_biblio(title="이방인", author="알베르 카뮈", publisher="민음사", series_title="세계문학전집"),
            evidence=self._build_evidence(title="이방인", author="알베르 카뮈", co_loan_books=[]),
        )

        self.assertEqual([subfield.value for subfield in result.fields[0].subfields], ["실존주의"])
        self.assertEqual(result.skipped_fields, [])

    def test_validate_output_keeps_independent_653_term_after_stronger_biblio_filter(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [
                            {"code": "a", "value": "홍학"},
                            {"code": "a", "value": "민음사 세계문학전집"},
                        ],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(
            raw_output,
            biblio=self._build_biblio(title="이방인", author="알베르 카뮈", publisher="민음사", series_title="세계문학전집"),
            evidence=self._build_evidence(title="이방인", author="알베르 카뮈", co_loan_books=[]),
        )

        self.assertEqual([subfield.value for subfield in result.fields[0].subfields], ["홍학"])
        self.assertEqual(result.skipped_fields, [])

    def test_validate_output_skips_056_when_a_is_empty(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "056",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": ""}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "low",
                        "evidence": {"from": ["keywords"], "reasoning": "테스트 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields, [])
        self.assertEqual(result.skipped_fields[0].tag, "056")
        self.assertEqual(result.skipped_fields[0].reason, "KDC 근거 부족: 056 생성 보류")
        self.assertIn("056 KDC 빈값 제거됨", result.warnings)

    def test_validate_output_skips_056_when_a_is_missing(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "056",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "2", "value": "6"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "low",
                        "evidence": {"from": ["keywords"], "reasoning": "테스트 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields, [])
        self.assertEqual(result.skipped_fields[0].tag, "056")
        self.assertEqual(result.skipped_fields[0].reason, "KDC 근거 부족: 056 생성 보류")
        self.assertIn("056 KDC 빈값 제거됨", result.warnings)

    def test_validate_output_keeps_056_when_a_is_present(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "056",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [
                            {"code": "a", "value": "813.7"},
                            {"code": "2", "value": "6"},
                        ],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "low",
                        "evidence": {"from": ["keywords"], "reasoning": "테스트 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields[0].tag, "056")
        self.assertEqual([(subfield.code, subfield.value) for subfield in result.fields[0].subfields], [("a", "813.7"), ("2", "6")])
        self.assertEqual(result.skipped_fields, [])

    def test_validate_output_skips_056_when_a_is_000(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "056",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "000"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "low",
                        "evidence": {"from": ["keywords"], "reasoning": "테스트 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields, [])
        self.assertEqual(result.skipped_fields[0].tag, "056")
        self.assertEqual(result.skipped_fields[0].reason, "KDC 근거 부족: 056 생성 보류")
        self.assertIn("056 KDC 기본값 000 제거됨", result.warnings)

    def test_validate_output_skips_082_when_a_is_000(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "082",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "000"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "low",
                        "evidence": {"from": ["keywords"], "reasoning": "테스트 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields, [])
        self.assertEqual(result.skipped_fields[0].tag, "082")
        self.assertEqual(result.skipped_fields[0].reason, "DDC 근거 부족: 082 생성 보류")
        self.assertIn("082 DDC 기본값 000 제거됨", result.warnings)

    def test_validate_output_keeps_082_when_a_is_present(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "082",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "843.914"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "low",
                        "evidence": {"from": ["keywords"], "reasoning": "테스트 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields[0].tag, "082")
        self.assertEqual([(subfield.code, subfield.value) for subfield in result.fields[0].subfields], [("a", "843.914")])
        self.assertEqual(result.skipped_fields, [])

    def test_validate_output_leaves_653_unchanged_without_context(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "채식주의"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual([subfield.value for subfield in result.fields[0].subfields], ["채식주의"])
        self.assertEqual(result.skipped_fields, [])

    def test_validate_output_assigns_generated_by_llm_for_inference_tags(self) -> None:
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "채식주의"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": {"from": ["keywords"], "reasoning": "키워드 근거"},
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields[0].generated_by, "llm")

    def test_validate_output_overrides_llm_reported_generated_by(self) -> None:
        """generated_by는 LLM 출력에 있더라도 신뢰하지 않고 서버가 재계산해야 한다.

        LLM 응답에서 온 필드는 태그와 무관하게 "llm"이다. 규칙 레이어가 만든
        필드만 "rule"을 가진다.
        """
        raw_output = json.dumps(
            {
                "fields": [
                    {
                        "tag": "020",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "9788936434120"}],
                        "source": "api",
                        "generated_by": "api",
                        "review_required": False,
                        "confidence": "high",
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            },
            ensure_ascii=False,
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields[0].generated_by, "llm")

    def _language_output(self, fields: list[dict[str, object]]) -> str:
        return json.dumps({"fields": fields, "skipped_fields": [], "warnings": []}, ensure_ascii=False)

    def test_validate_output_removes_generic_korean_546(self) -> None:
        """'한국어로 된 자료'는 언어주기 근거가 아니다. 중간발표 결과의 대표 과잉 생성."""

        raw_output = self._language_output(
            [
                {
                    "tag": "546",
                    "indicator1": " ",
                    "indicator2": " ",
                    "subfields": [{"code": "a", "value": "한국어로 된 자료"}],
                    "source": "ai_inference",
                    "review_required": True,
                    "confidence": "medium",
                    "evidence": {"from": ["title"], "reasoning": "표제가 한국어"},
                }
            ]
        )

        result = validate_output(raw_output, evidence=self._build_evidence())

        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["546"])

    def test_validate_output_keeps_translation_546(self) -> None:
        raw_output = self._language_output(
            [
                {
                    "tag": "546",
                    "indicator1": " ",
                    "indicator2": " ",
                    "subfields": [{"code": "a", "value": "스페인어 원작을 한국어로 번역"}],
                    "source": "ai_inference",
                    "review_required": True,
                    "confidence": "medium",
                    "evidence": {"from": ["description"], "reasoning": "번역 정황 확인"},
                }
            ]
        )

        result = validate_output(
            raw_output,
            evidence=self._build_evidence(description="스페인어 원작을 한국어로 번역"),
        )

        self.assertEqual([field.tag for field in result.fields], ["546"])

    def test_validate_output_removes_041_without_translation_signal(self) -> None:
        """본문언어 하나만 있는 041은 008/35-37에 없는 정보를 더하지 않는다."""

        raw_output = self._language_output(
            [
                {
                    "tag": "041",
                    "indicator1": "1",
                    "indicator2": " ",
                    "subfields": [{"code": "a", "value": "kor"}],
                    "source": "ai_inference",
                    "review_required": True,
                    "confidence": "low",
                    "evidence": {"from": ["description"], "reasoning": "한국어 자료"},
                }
            ]
        )

        result = validate_output(raw_output, evidence=self._build_evidence())

        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["041"])

    def test_validate_output_keeps_041_with_original_language(self) -> None:
        raw_output = self._language_output(
            [
                {
                    "tag": "041",
                    "indicator1": "1",
                    "indicator2": " ",
                    "subfields": [{"code": "a", "value": "kor"}, {"code": "h", "value": "ger"}],
                    "source": "ai_inference",
                    "review_required": True,
                    "confidence": "medium",
                    "evidence": {"from": ["description"], "reasoning": "독일어 원작 번역"},
                }
            ]
        )

        result = validate_output(raw_output, evidence=self._build_evidence(description="독일어 원작을 한국어로 번역"))

        self.assertEqual([field.tag for field in result.fields], ["041"])

    def _inference_field(self, tag: str, subfields: list[dict[str, str]], indicator1: str = " ") -> dict[str, object]:
        return {
            "tag": tag,
            "indicator1": indicator1,
            "indicator2": " ",
            "subfields": subfields,
            "source": "ai_inference",
            "review_required": True,
            "confidence": "low",
            "evidence": {"from": ["author"], "reasoning": "검수용 후보"},
        }

    def test_validate_output_removes_negated_546_even_with_keyword(self) -> None:
        """'번역' 키워드가 있어도 근거가 없다는 문장은 언어주기가 아니다."""

        raw_output = self._language_output(
            [self._inference_field("546", [{"code": "a", "value": "한국어 자료로 보이나 번역이나 다국어 정황은 확인되지 않음"}])]
        )

        result = validate_output(raw_output, evidence=self._build_evidence())

        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["546"])

    def test_validate_output_removes_246_identical_to_title(self) -> None:
        raw_output = self._language_output(
            [self._inference_field("246", [{"code": "a", "value": "끝까지 해 보자 때밀이 장갑"}], indicator1="3")]
        )

        result = validate_output(raw_output, biblio=self._build_biblio(title="끝까지 해 보자, 때밀이 장갑!"))

        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["246"])

    def test_validate_output_keeps_246_with_different_title(self) -> None:
        raw_output = self._language_output(
            [self._inference_field("246", [{"code": "a", "value": "Dove andiamo quando moriamo?"}], indicator1="1")]
        )

        result = validate_output(raw_output, biblio=self._build_biblio(title="우리는 죽으면 어디로 가요?"))

        self.assertEqual([field.tag for field in result.fields], ["246"])

    def test_validate_output_removes_publisher_as_710(self) -> None:
        raw_output = self._language_output(
            [
                self._inference_field("710", [{"code": "a", "value": "마음산책"}], indicator1="2"),
                self._inference_field("710", [{"code": "a", "value": "생능출판사"}, {"code": "e", "value": "출판"}], indicator1="2"),
            ]
        )

        result = validate_output(raw_output, biblio=self._build_biblio(publisher="마음산책"))

        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["710"])

    def test_validate_output_keeps_corporate_author_710(self) -> None:
        raw_output = self._language_output(
            [self._inference_field("710", [{"code": "a", "value": "국립국어원"}, {"code": "e", "value": "편"}], indicator1="2")]
        )

        result = validate_output(raw_output, biblio=self._build_biblio(publisher="창비"))

        self.assertEqual([field.tag for field in result.fields], ["710"])

    def test_validate_output_removes_summary_and_translation_500(self) -> None:
        """책소개 요약은 520, 번역 사실은 041/546 범위다. 500으로 남기지 않는다."""

        raw_output = self._language_output(
            [
                self._inference_field("500", [{"code": "a", "value": "조선 시대 배경의 창작동화"}]),
                self._inference_field("500", [{"code": "a", "value": "제1회 소원청소년문학상 대상 수상작"}]),
                self._inference_field("500", [{"code": "a", "value": "번역서"}]),
            ]
        )

        result = validate_output(raw_output)

        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["500"])

    def test_validate_output_keeps_allowed_500_types(self) -> None:
        raw_output = self._language_output(
            [
                self._inference_field("500", [{"code": "a", "value": "원저자명: Frantz Kafka"}]),
                self._inference_field("500", [{"code": "a", "value": "공저자: 윤수란, 정명섭, 이지유"}]),
                self._inference_field("500", [{"code": "a", "value": "감수: 장윤석, 송지희"}]),
                self._inference_field("500", [{"code": "a", "value": "하시모토 다카시의 한자명은 '橋本孝' 임"}]),
            ]
        )

        result = validate_output(raw_output)

        self.assertEqual([field.tag for field in result.fields], ["500", "500", "500", "500"])

    def _inferred_field(self, tag: str, subfields: list[tuple[str, str]]) -> dict[str, object]:
        return {
            "tag": tag,
            "indicator1": " ",
            "indicator2": " ",
            "subfields": [{"code": code, "value": value} for code, value in subfields],
            "source": "ai_inference",
            "review_required": True,
            "confidence": "medium",
            "evidence": {"from": ["description"], "reasoning": "모델의 주장은 독립 근거가 아님"},
        }

    def test_language_claims_require_actual_available_evidence(self) -> None:
        raw_output = self._language_output([
            self._inferred_field("041", [("a", "kor"), ("h", "eng")]),
            self._inferred_field("546", [("a", "영어 원작을 한국어로 번역")]),
        ])
        unavailable = self._build_evidence(
            description="영어 원작을 한국어로 번역",
            translation_signals={"detected": True, "hints": ["옮김"]},
            available={"keywords": False, "description": False, "co_loan_books": False, "translation_signals": False},
        )
        hints_only = self._build_evidence(
            author="영국 작가 지음; 한국인 옮김",
            translation_signals={"detected": True, "hints": ["옮김"]},
            available={"keywords": False, "description": False, "co_loan_books": False, "translation_signals": True},
        )
        for evidence in (None, self._build_evidence(), unavailable):
            with self.subTest(evidence=evidence):
                result = validate_output(raw_output, evidence=evidence)
                self.assertEqual(result.fields, [])
                self.assertEqual({item.tag for item in result.skipped_fields}, {"041", "546"})

        # 번역 정황이 확인되면 본문언어 kor은 남는다. 정답 MARC에서 번역서 212권이
        # 모두 041을 갖는데, 원저작 언어를 모른다고 041 전체를 버리면 전부 누락된다.
        kept = validate_output(raw_output, evidence=hints_only)
        self.assertEqual([field.tag for field in kept.fields], ["041"])
        self.assertEqual([(s.code, s.value) for s in kept.fields[0].subfields], [("a", "kor")])
        self.assertEqual(kept.fields[0].indicator1, "1")
        self.assertEqual({item.tag for item in kept.skipped_fields}, {"546"})

    def test_available_translation_hint_only_supports_language_free_note(self) -> None:
        raw_output = self._language_output([
            self._inferred_field("041", [("a", "kor")]),
            self._inferred_field("546", [("a", "번역서")]),
        ])
        for available in (True, False):
            with self.subTest(available=available):
                evidence = self._build_evidence(
                    translation_signals={"detected": True, "hints": ["옮김"]},
                    available={"keywords": False, "description": False, "co_loan_books": False, "translation_signals": available},
                )
                result = validate_output(raw_output, evidence=evidence)
                self.assertEqual([field.tag for field in result.fields], ["041", "546"] if available else [])

    def test_language_roles_do_not_confuse_original_with_translated_language(self) -> None:
        raw_output = self._language_output([
            self._inferred_field("041", [("a", "eng"), ("h", "kor")]),
            self._inferred_field("546", [("a", "한국어 원작을 영어로 번역")]),
        ])
        result = validate_output(raw_output, evidence=self._build_evidence(description="영어 원작을 한국어로 번역"))
        self.assertEqual(result.fields, [])

    def test_language_policy_keeps_explicit_multilingual_body_without_translation(self) -> None:
        raw_output = self._language_output([
            self._inferred_field("041", [("a", "kor"), ("a", "eng")]),
            self._inferred_field("546", [("a", "한국어와 영어로 병기")]),
        ])
        result = validate_output(raw_output, evidence=self._build_evidence(description="한국어와 영어로 병기"))
        self.assertEqual([field.tag for field in result.fields], ["041", "546"])
        self.assertEqual([subfield.value for subfield in result.fields[0].subfields], ["kor", "eng"])

    def test_language_policy_preserves_supported_roles_and_removes_fabricated_original(self) -> None:
        raw_output = self._language_output([
            self._inferred_field("041", [("a", "kor"), ("b", "eng"), ("f", "jpn"), ("h", "ger")]),
        ])
        result = validate_output(
            raw_output,
            evidence=self._build_evidence(description="본문 언어: 한국어. 영어 요약. 일본어 목차."),
        )
        self.assertEqual([(sf.code, sf.value) for sf in result.fields[0].subfields], [
            ("a", "kor"), ("b", "eng"), ("f", "jpn"),
        ])

    def test_language_policy_supports_translation_word_order_and_literal_codes(self) -> None:
        for description in (
            "한국어로 번역된 영어 원작",
            "원저작 언어: eng. 본문 언어: kor. 한국어로 번역.",
        ):
            with self.subTest(description=description):
                result = validate_output(
                    self._language_output([self._inferred_field("041", [("a", "kor"), ("h", "eng")])]),
                    evidence=self._build_evidence(description=description),
                )
                self.assertEqual([(sf.code, sf.value) for sf in result.fields[0].subfields], [("a", "kor"), ("h", "eng")])

    def test_language_policy_defers_unmapped_languages_without_guessing(self) -> None:
        result = validate_output(
            self._language_output([self._inferred_field("041", [("h", "ita")])]),
            evidence=self._build_evidence(description="이탈리아어 원작"),
        )
        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["041"])

    def test_language_note_cannot_add_parenthetical_claim_or_truncate_negation(self) -> None:
        for description, note in (
            ("영어 원작을 한국어로 번역", "영어 원작(독일어 중역)을 한국어로 번역"),
            ("영어 원작을 한국어로 번역한 자료가 아니다", "영어 원작을 한국어로 번역"),
        ):
            with self.subTest(description=description):
                result = validate_output(
                    self._language_output([self._inferred_field("546", [("a", note)])]),
                    evidence=self._build_evidence(description=description),
                )
                self.assertEqual(result.fields, [])

    def test_grounded_note_stating_absence_of_evidence_is_still_removed(self) -> None:
        """입력에 그대로 있어도 '보이나'처럼 불확실을 적은 문장은 언어주기가 아니다."""

        result = validate_output(
            self._language_output([self._inferred_field("546", [("a", "번역서로 보이나")])]),
            evidence=self._build_evidence(description="번역서로 보이나 원작 언어는 확인 불가"),
        )

        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["546"])

    def test_independent_keyword_survives_title_overlap_but_not_full_name_pollution(self) -> None:
        raw_output = self._language_output([
            self._inferred_field("653", [("a", "인공지능"), ("a", "인공지능의 이해"), ("a", "출판사")]),
        ])
        for available in (True, False):
            with self.subTest(available=available):
                result = validate_output(
                    raw_output,
                    biblio=self._build_biblio(title="인공지능의 이해", publisher="출판사", series_title=""),
                    evidence=self._build_evidence(
                        keywords=[{"word": term, "weight": 1} for term in ("인공지능", "인공지능의 이해", "출판사")],
                        available={"keywords": available, "description": False, "co_loan_books": False, "translation_signals": False},
                    ),
                )
                terms = [sf.value for field in result.fields for sf in field.subfields]
                self.assertEqual(terms, ["인공지능"] if available else [])

    def test_independent_keyword_survives_co_loan_title_overlap(self) -> None:
        result = validate_output(
            self._language_output([self._inferred_field("653", [("a", "인공지능")])]),
            evidence=self._build_evidence(
                keywords=[{"word": "인공지능", "weight": 1}],
                co_loan_books=[{"bookname": "인공지능의 이해", "isbn13": "9780000000000", "authors": "저자"}],
            ),
        )
        self.assertEqual([sf.value for sf in result.fields[0].subfields], ["인공지능"])

    def test_language_note_paraphrase_of_supported_relationship_survives(self) -> None:
        """표현만 다르고 입력이 뒷받침하는 관계만 말하는 언어주기는 남긴다."""

        result = validate_output(
            self._language_output([self._inferred_field("546", [("a", "영어 원작의 한국어 번역본")])]),
            evidence=self._build_evidence(description="영어 원작을 한국어로 번역"),
        )

        self.assertEqual([sf.value for sf in result.fields[0].subfields], ["영어 원작의 한국어 번역본"])

    def test_language_roles_read_common_particles_and_source_language_phrasing(self) -> None:
        for description in (
            "원작은 영어이며 한국어로 번역하였다",
            "원작의 언어는 영어이고 본문은 한국어다",
            "영어 원서를 한국어로 옮김",
        ):
            with self.subTest(description=description):
                result = validate_output(
                    self._language_output([self._inferred_field("041", [("a", "kor"), ("h", "eng")])]),
                    evidence=self._build_evidence(description=description),
                )
                self.assertEqual(
                    [(sf.code, sf.value) for sf in result.fields[0].subfields], [("a", "kor"), ("h", "eng")]
                )

    def test_positive_statement_with_negation_syllable_still_supports_language_fields(self) -> None:
        """'빠짐없이'는 번역 사실을 부정하지 않는다. 음절만 보고 근거를 버리지 않는다."""

        result = validate_output(
            self._language_output([
                self._inferred_field("041", [("a", "kor"), ("h", "eng")]),
                self._inferred_field("546", [("a", "빠짐없이 영어 원작을 한국어로 번역하였다")]),
            ]),
            evidence=self._build_evidence(description="빠짐없이 영어 원작을 한국어로 번역하였다"),
        )

        self.assertEqual([field.tag for field in result.fields], ["041", "546"])
        self.assertEqual(result.skipped_fields, [])

    def test_negation_after_language_claim_still_removes_fields(self) -> None:
        for description in (
            "영어 원작이나 한국어 번역본은 아님",
            "번역 여부는 확인할 수 없음",
            "원작 언어는 미상",
        ):
            with self.subTest(description=description):
                result = validate_output(
                    self._language_output([
                        self._inferred_field("041", [("a", "kor"), ("h", "eng")]),
                        self._inferred_field("546", [("a", "영어 원작의 한국어 번역본")]),
                    ]),
                    evidence=self._build_evidence(description=description),
                )
                self.assertEqual(result.fields, [])

    def test_041_translation_indicator_follows_supported_translation_context(self) -> None:
        translated = self._inferred_field("041", [("a", "kor"), ("h", "eng")])
        translated["indicator1"] = "0"
        result = validate_output(
            self._language_output([translated]),
            evidence=self._build_evidence(description="영어 원작을 한국어로 번역"),
        )
        self.assertEqual(result.fields[0].indicator1, "1")

        multilingual = self._inferred_field("041", [("a", "kor"), ("a", "eng")])
        multilingual["indicator1"] = "0"
        result = validate_output(
            self._language_output([multilingual]),
            evidence=self._build_evidence(description="한국어와 영어로 병기"),
        )
        self.assertEqual(result.fields[0].indicator1, "0")

    def test_language_note_rejects_extra_language_or_unexplained_mention(self) -> None:
        for note in (
            "영어와 독일어 원작의 한국어 번역본",
            "영어 원작의 한국어 번역본이며 일본어 자막 수록",
            "영어 원작의 한국어 번역본, 1945년 초판",
            "영어 원작의 한국어 번역본이며 점자도 수록",
            "영어 원작의 한국어 번역본; 원문은 삭제됨",
        ):
            with self.subTest(note=note):
                result = validate_output(
                    self._language_output([self._inferred_field("546", [("a", note)])]),
                    evidence=self._build_evidence(description="영어 원작을 한국어로 번역"),
                )
                self.assertEqual(result.fields, [])
                self.assertEqual([item.tag for item in result.skipped_fields], ["546"])

    def test_independent_653_term_survives_publisher_and_co_loan_substrings(self) -> None:
        for biblio, evidence in (
            (
                self._build_biblio(publisher="길", title="숲", series_title=""),
                self._build_evidence(keywords=[{"word": "길찾기", "weight": 1}]),
            ),
            (
                self._build_biblio(publisher="창비", title="길", series_title=""),
                self._build_evidence(keywords=[{"word": "길찾기", "weight": 1}]),
            ),
            (
                self._build_biblio(publisher="창비", title="숲", series_title=""),
                self._build_evidence(
                    keywords=[{"word": "길찾기", "weight": 1}],
                    co_loan_books=[{"bookname": "길", "isbn13": "9780000000000", "authors": "저자"}],
                ),
            ),
        ):
            with self.subTest(publisher=biblio.publisher, title=biblio.title):
                result = validate_output(
                    self._language_output([self._inferred_field("653", [("a", "길찾기")])]),
                    biblio=biblio,
                    evidence=evidence,
                )
                self.assertEqual([sf.value for sf in result.fields[0].subfields], ["길찾기"])

    def test_653_term_matching_bibliographic_name_is_still_removed(self) -> None:
        result = validate_output(
            self._language_output([self._inferred_field("653", [("a", "길")])]),
            biblio=self._build_biblio(publisher="길", title="숲", series_title=""),
            evidence=self._build_evidence(keywords=[{"word": "길", "weight": 1}]),
        )

        self.assertEqual(result.fields, [])
        self.assertEqual([item.tag for item in result.skipped_fields], ["653"])


if __name__ == "__main__":
    _ = unittest.main()
