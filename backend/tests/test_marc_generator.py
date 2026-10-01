import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.schemas.llm import LLMInputPayload
from backend.services.marc_generator import generate_marc


def payload() -> LLMInputPayload:
    return LLMInputPayload.model_validate(
        {
            "isbn": "9788936434120",
            "biblio": {
                "found": True,
                "isbn_ea": "9788936434120",
                "title": "채식주의자",
                "author": "한강 지음",
                "publisher": "창비",
            },
            "evidence": {
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


def llm_field(tag: str, value: str) -> dict:
    return {
        "tag": tag,
        "source": "api",
        "indicator1": " ",
        "indicator2": " ",
        "subfields": [{"code": "a", "value": value}],
        "review_required": True,
        "confidence": "medium",
    }


class MarcGeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def _generate(self, request: LLMInputPayload, fields: list[dict]):
        raw = json.dumps({"fields": fields, "skipped_fields": [], "warnings": []})
        # Only the external model is substituted; prompt, validator and rule merge are real.
        with patch(
            "backend.services.marc_generator.llm_client.generate",
            new=AsyncMock(return_value=raw),
        ):
            return await generate_marc(request)

    async def test_empty_llm_keeps_api_facts_and_explains_exclusions(self) -> None:
        result = await self._generate(payload(), [])

        self.assertEqual([field.tag for field in result.fields], ["020", "245", "260"])
        title = next(field for field in result.fields if field.tag == "245")
        self.assertEqual(
            [(sub.code, sub.value) for sub in title.subfields],
            [("a", "채식주의자"), ("d", "한강 지음")],
        )
        skipped = {item.tag for item in result.skipped_fields}
        self.assertTrue({"650", "830", "950"} <= skipped)

    async def test_subject_validation_uses_both_biblio_and_input_evidence(self) -> None:
        request = payload()
        request.biblio.title = "인공지능의 이해"
        request.evidence = type(request.evidence).model_validate(
            {
                **request.evidence.model_dump(),
                "keywords": [{"word": "인공지능", "weight": 0.9}],
                "available": {
                    **request.evidence.available.model_dump(),
                    "keywords": True,
                },
            }
        )
        subject = llm_field("653", "인공지능")
        subject["source"] = "ai_inference"
        subject["evidence"] = {
            "from": ["keywords"],
            "keywords_used": ["인공지능"],
            "reasoning": "입력 키워드에 있는 주제",
        }
        subject["subfields"].append({"code": "a", "value": "인공지능의 이해"})

        result = await self._generate(request, [subject])

        # biblio가 없으면 서명 전체가 남고, evidence가 없으면 정상 주제어도 삭제된다.
        self.assertEqual(
            [
                sub.value
                for field in result.fields if field.tag == "653"
                for sub in field.subfields if sub.code == "a"
            ],
            ["인공지능"],
        )

    async def test_generate_marc_ignores_llm_output_for_rule_tags(self) -> None:
        wrong_title = llm_field("245", "엉뚱한 표제")
        wrong_title["subfields"].append({"code": "c", "value": "엉뚱한 저자"})
        result = await self._generate(payload(), [wrong_title])

        titles = [field for field in result.fields if field.tag == "245"]
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0].generated_by, "rule")
        self.assertEqual(
            [(sub.code, sub.value) for sub in titles[0].subfields],
            [("a", "채식주의자"), ("d", "한강 지음")],
        )

    async def test_forbidden_and_unrequested_fields_never_reach_final_record(self) -> None:
        result = await self._generate(
            payload(),
            [
                llm_field("700", "한강"),
                llm_field("830", "확인되지 않은 총서"),
                llm_field("950", "종이책"),
                llm_field("999", "요청하지 않은 값"),
            ],
        )

        self.assertEqual([field.tag for field in result.fields], ["020", "245", "260", "700"])
        self.assertEqual(result.fields[-1].subfields[0].value, "한강")
        self.assertTrue({"830", "950", "999"} <= {item.tag for item in result.skipped_fields})

    async def test_explicit_skip_overrides_requested_llm_field(self) -> None:
        request = payload()
        request.generate_options.skipped_by_default.append("700")
        result = await self._generate(request, [llm_field("700", "한강")])

        self.assertNotIn("700", {field.tag for field in result.fields})
        self.assertIn("700", {item.tag for item in result.skipped_fields})


if __name__ == "__main__":
    unittest.main()
