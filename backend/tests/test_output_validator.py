import json
import unittest

from backend.services.output_validator import OutputValidationError, validate_output


class OutputValidatorTests(unittest.TestCase):
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


if __name__ == "__main__":
    _ = unittest.main()
