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

        self.assertEqual([subfield.value for subfield in result.fields[0].subfields], ["폭력"])
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
                            {"code": "a", "value": "채식주의"},
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
                        "subfields": [{"code": "a", "value": "채식주의"}],
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


if __name__ == "__main__":
    _ = unittest.main()
