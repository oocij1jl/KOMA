import asyncio
import unittest
from typing import cast
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.lookup import LookupResponseSchema
from backend.services.llm_input_builder import build_llm_input
from backend.services.lookup_service import lookup_one


class GenerateSchemaTests(unittest.TestCase):
    def test_build_llm_input_excludes_raw_and_preserves_evidence(self) -> None:
        lookup_result = LookupResponseSchema.model_validate(
            {
                "isbn": "9788936434120",
                "biblio": {
                    "found": True,
                    "isbn_ea": "9788936434120",
                    "cover_url": "https://example.com/cover.jpg",
                    "field_sources": {},
                },
                "evidence": {
                    "keywords": [{"word": "도서관", "weight": 0.9}],
                    "description": "설명",
                    "co_loan_books": [],
                    "title": "예시 제목",
                    "author": "홍길동 옮김",
                    "kdc_from_api": "001",
                    "ddc_from_api": "100",
                    "translation_signals": {"detected": True, "hints": ["'옮김' 표현 발견"]},
                    "available": {
                        "keywords": True,
                        "description": True,
                        "co_loan_books": False,
                        "translation_signals": True,
                    },
                },
                "raw": {
                    "nl": {"found": True},
                    "d4l_detail": {"found": True},
                    "d4l_keyword": {"found": True},
                    "d4l_usage": {"found": False},
                },
            }
        )

        payload = build_llm_input(lookup_result)
        dumped: dict[str, object] = payload.model_dump()
        evidence = cast(dict[str, object], dumped["evidence"])
        available = cast(dict[str, bool], evidence["available"])
        translation_signals = cast(dict[str, object], evidence["translation_signals"])
        field_evidence_map = cast(dict[str, dict[str, object]], dumped["field_evidence_map"])
        generate_options = cast(dict[str, list[str]], dumped["generate_options"])

        self.assertNotIn("raw", dumped)
        self.assertTrue(available["keywords"])
        self.assertTrue(available["translation_signals"])
        self.assertTrue(cast(bool, translation_signals["detected"]))
        self.assertIn("field_evidence_map", dumped)
        self.assertIn("653", field_evidence_map)
        self.assertEqual(cast(list[object], field_evidence_map["650"]["evidence_sources"]), [])
        self.assertTrue(cast(bool, field_evidence_map["650"]["skip_allowed"]))
        self.assertEqual(
            cast(str, field_evidence_map["650"]["rag_notes"]),
            "MVP 기본 skip — 통제 주제명은 표목표 대조 필요",
        )
        self.assertEqual(generate_options["review_required_fields"], ["653", "056", "082"])
        self.assertEqual(generate_options["skipped_by_default"], ["650"])
        self.assertNotIn("650", generate_options["required_fields"])
        self.assertNotIn("650", generate_options["review_required_fields"])
        self.assertIn("710", generate_options["required_fields"])

    def test_lookup_one_uses_isbn13_for_upstream_calls(self) -> None:
        async def run_test() -> None:
            with patch(
                "backend.services.lookup_service.fetch_nl_isbn",
                new=AsyncMock(return_value={"source": "nl.go.kr", "found": True, "isbn": "9788936434120"}),
            ) as nl_mock, patch(
                "backend.services.lookup_service.fetch_d4l_detail",
                new=AsyncMock(return_value={"source": "data4library.kr", "found": True, "isbn13": "9788936434120"}),
            ) as detail_mock, patch(
                "backend.services.lookup_service.fetch_d4l_keywords",
                new=AsyncMock(return_value={"source": "keywordList", "found": False, "keywords": []}),
            ) as keyword_mock, patch(
                "backend.services.lookup_service.fetch_d4l_usage",
                new=AsyncMock(return_value={"source": "usageAnalysisList", "found": False, "co_loan_books": []}),
            ) as usage_mock:
                async with httpx.AsyncClient() as client:
                    result = await lookup_one(client, "89-364-3412-X")

                self.assertEqual(result["isbn"], "9788936434120")
                nl_mock.assert_awaited_once_with(client, "9788936434120")
                detail_mock.assert_awaited_once_with(client, "9788936434120")
                keyword_mock.assert_awaited_once_with(client, "9788936434120")
                usage_mock.assert_awaited_once_with(client, "9788936434120")

        asyncio.run(run_test())

    def test_generate_routes_return_prompt_with_primary_and_alias(self) -> None:
        lookup_payload: dict[str, object] = {
            "isbn": "9788936434120",
            "biblio": {
                "found": True,
                "isbn_ea": "9788936434120",
                "title": "채식주의자",
                "author": "한강 지음",
                "publisher": "창비",
                "publish_year": "2022",
                "kdc": "813.7",
                "page": "247 p.",
                "description": "채식주의를 선택한 인물을 둘러싼 한국 장편소설.",
                "field_sources": {},
            },
            "evidence": {
                "keywords": [{"word": "채식주의", "weight": 0.91}],
                "description": "채식주의를 선택한 인물을 둘러싼 한국 장편소설.",
                "co_loan_books": [],
                "title": "채식주의자",
                "author": "한강 지음",
                "kdc_from_api": "813.7",
                "ddc_from_api": "",
                "translation_signals": {"detected": False, "hints": []},
                "available": {
                    "keywords": True,
                    "description": True,
                    "co_loan_books": False,
                    "translation_signals": False,
                },
            },
            "raw": {"nl": {}, "d4l_detail": {}, "d4l_keyword": {}, "d4l_usage": {}},
            "found": True,
        }

        with patch("backend.routers.generate.lookup_one", new=AsyncMock(return_value=lookup_payload)):
            client = TestClient(app)
            primary = client.post("/api/generate/marc", json={"isbn": "89-364-3412-X"})
            alias = client.post("/api/generate", json={"isbn": "89-364-3412-X"})

        self.assertEqual(primary.status_code, 200)
        self.assertEqual(alias.status_code, 200)
        self.assertTrue(primary.headers["content-type"].startswith("text/plain"))
        self.assertTrue(alias.headers["content-type"].startswith("text/plain"))
        self.assertEqual(primary.text, alias.text)

        self.assertIn("9788936434120", primary.text)
        self.assertIn("채식주의자", primary.text)
        self.assertIn("813.7", primary.text)
        self.assertIn("247 p.", primary.text)
        self.assertIn("채식주의를 선택한 인물을 둘러싼 한국 장편소설.", primary.text)
        self.assertIn("FIELD_EVIDENCE_MAP", primary.text)
        self.assertIn("RAG RULES", primary.text)

    def test_generate_routes_build_prompt_even_with_partial_evidence(self) -> None:
        lookup_payload: dict[str, object] = {
            "isbn": "9788936434120",
            "biblio": {
                "found": True,
                "isbn_ea": "9788936434120",
                "title": "예시 제목",
                "author": "예시 저자",
                "publisher": "예시 출판사",
                "field_sources": {},
            },
            "evidence": {
                "keywords": [],
                "description": "",
                "co_loan_books": [],
                "title": "예시 제목",
                "author": "예시 저자",
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
            "raw": {"nl": {}, "d4l_detail": {}, "d4l_keyword": {}, "d4l_usage": {}},
            "found": True,
        }

        with patch("backend.routers.generate.lookup_one", new=AsyncMock(return_value=lookup_payload)):
            client = TestClient(app)
            response = client.post("/api/generate/marc", json={"isbn": "89-364-3412-X"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        self.assertIn("예시 제목", response.text)
        self.assertIn('"keywords": false', response.text)
        self.assertIn('"co_loan_books": false', response.text)

    def test_generate_routes_return_404_when_lookup_not_found(self) -> None:
        lookup_payload: dict[str, object] = {
            "isbn": "9788936434120",
            "biblio": {
                "found": False,
                "isbn_ea": "",
                "field_sources": {},
            },
            "evidence": {
                "keywords": [],
                "description": "",
                "co_loan_books": [],
                "title": "",
                "author": "",
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
            "raw": {"nl": {}, "d4l_detail": {}, "d4l_keyword": {}, "d4l_usage": {}},
            "found": False,
        }

        with patch("backend.routers.generate.lookup_one", new=AsyncMock(return_value=lookup_payload)):
            client = TestClient(app)
            response = client.post("/api/generate/marc", json={"isbn": "89-364-3412-X"})

        self.assertEqual(response.status_code, 404)
        response_json = cast(dict[str, object], response.json())
        detail = response_json["detail"]
        if not isinstance(detail, str):
            self.fail("detail should be a string")
        self.assertIn("ISBN 9788936434120", detail)

    def test_generate_routes_return_422_for_invalid_isbn(self) -> None:
        client = TestClient(app)
        response = client.post("/api/generate/marc", json={"isbn": "abc"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "유효하지 않은 ISBN 형식: 'abc'")

    def test_generate_routes_return_422_for_invalid_isbn13_checksum(self) -> None:
        client = TestClient(app)
        response = client.post("/api/generate/marc", json={"isbn": "9788936434121"})

        self.assertEqual(response.status_code, 422)
        response_json = cast(dict[str, object], response.json())
        detail = response_json["detail"]
        if not isinstance(detail, str):
            self.fail("detail should be a string")
        self.assertIn("ISBN-13 체크섬 오류", detail)


if __name__ == "__main__":
    _ = unittest.main()
