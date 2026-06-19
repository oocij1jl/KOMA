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
        expected = GenerateResult.model_validate({"fields": [], "skipped_fields": [], "warnings": []})

        with patch("backend.services.marc_generator.build_prompt", return_value="prompt"), patch(
            "backend.services.marc_generator.llm_client.generate",
            new=AsyncMock(return_value=raw_output),
        ), patch("backend.services.marc_generator.validate_output", return_value=expected) as validate_mock:
            result = await generate_marc(payload)

        self.assertEqual(result, expected)
        validate_mock.assert_called_once_with(raw_output, biblio=payload.biblio, evidence=payload.evidence)


if __name__ == "__main__":
    _ = unittest.main()
