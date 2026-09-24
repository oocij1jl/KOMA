import unittest
from unittest.mock import AsyncMock, patch

from backend.schemas.llm import LLMInputPayload
from backend.schemas.llm_output import GenerateResult
from backend.services.marc_generator import generate_marc


class MarcGeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_marc_passes_biblio_and_evidence_to_validator(self) -> None:
        payload = LLMInputPayload.model_validate(
            {
                "isbn": "9788936434120",
                "biblio": {
                    "found": True,
                    "isbn_ea": "9788936434120",
                    "title": "채식주의자",
                    "author": "한강 지음",
                    "publisher": "창비",
                    "series_title": "창비 장편소설",
                    "field_sources": {},
                },
                "evidence": {
                    "keywords": [{"word": "채식주의", "weight": 0.91}],
                    "description": "채식주의를 선택한 인물을 둘러싼 한국 장편소설.",
                    "co_loan_books": [],
                    "title": "채식주의자",
                    "author": "한강 지음",
                    "kdc_from_api": "813.7",
                    "ddc_from_api": "895.735",
                    "translation_signals": {"detected": False, "hints": []},
                    "available": {
                        "keywords": True,
                        "description": True,
                        "co_loan_books": False,
                        "translation_signals": False,
                    },
                },
            }
        )
        raw_output = '{"fields":[],"skipped_fields":[],"warnings":[]}'
        validated = GenerateResult.model_validate({"fields": [], "skipped_fields": [], "warnings": []})

        with patch("backend.services.marc_generator.build_prompt", return_value="prompt"), patch(
            "backend.services.marc_generator.llm_client.generate",
            new=AsyncMock(return_value=raw_output),
        ), patch("backend.services.marc_generator.validate_output", return_value=validated) as validate_mock:
            result = await generate_marc(payload)

        validate_mock.assert_called_once_with(raw_output, biblio=payload.biblio, evidence=payload.evidence)
        # 245는 LLM 출력이 비어 있어도 규칙 레이어가 biblio에서 만든다.
        self.assertEqual([field.tag for field in result.fields], ["245"])
        self.assertEqual(result.fields[0].generated_by, "rule")

    async def test_generate_marc_ignores_llm_output_for_rule_tags(self) -> None:
        """LLM이 245를 만들어도 규칙 레이어 결과가 최종값이다."""

        payload = LLMInputPayload.model_validate(
            {
                "isbn": "9788936434120",
                "biblio": {
                    "found": True,
                    "isbn_ea": "9788936434120",
                    "title": "채식주의자",
                    "author": "한강 지음",
                    "field_sources": {},
                },
                "evidence": {
                    "keywords": [],
                    "description": "",
                    "co_loan_books": [],
                    "title": "채식주의자",
                    "author": "한강 지음",
                    "kdc_from_api": "",
                    "ddc_from_api": "",
                    "translation_signals": {"detected": False, "hints": []},
                    "available": {
                        "keywords": False,
                        "description": False,
                        "co_loan_books": False,
                        "translation_signals": False,
                    },
                },
            }
        )
        llm_result = GenerateResult.model_validate(
            {
                "fields": [
                    {
                        "tag": "245",
                        "source": "api",
                        "generated_by": "llm",
                        "indicator1": "1",
                        "indicator2": "0",
                        "subfields": [{"code": "a", "value": "엉뚱한 표제"}, {"code": "c", "value": "한강"}],
                        "review_required": False,
                        "confidence": "high",
                    }
                ],
                "skipped_fields": [],
                "warnings": [],
            }
        )

        with patch("backend.services.marc_generator.build_prompt", return_value="prompt"), patch(
            "backend.services.marc_generator.llm_client.generate",
            new=AsyncMock(return_value="{}"),
        ), patch("backend.services.marc_generator.validate_output", return_value=llm_result):
            result = await generate_marc(payload)

        self.assertEqual(len(result.fields), 1)
        field = result.fields[0]
        self.assertEqual(field.generated_by, "rule")
        self.assertEqual([subfield.code for subfield in field.subfields], ["a", "d"])
        self.assertEqual(field.subfields[0].value, "채식주의자")
        self.assertTrue(any("규칙 레이어" in warning for warning in result.warnings))


if __name__ == "__main__":
    _ = unittest.main()
