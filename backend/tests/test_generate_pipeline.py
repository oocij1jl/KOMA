"""/api/generate/marc 전체 경로 통합 테스트.

외부 API와 LLM만 대역으로 바꾸고, 규칙 레이어와 검증기는 실제 코드를 쓴다.
중간발표 결과에서 확인된 오류(245 ▼c, 근거 없는 546)가 최종 응답에서
사라지는지, API 값이 규칙대로 배치되는지 확인한다.
"""

import json
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.main import app


LOOKUP_RESULT: dict[str, Any] = {
    "found": True,
    "isbn": "9791194630678",
    "biblio": {
        "found": True,
        "isbn_ea": "9791194630678",
        "isbn_add_code": "13000",
        "price": "₩13000",
        "title": "모두의 노션 AI : 초보자도 바로 써먹는 노션 입문서",
        "author": "임대균 오가연 지음",
        "publisher": "생능북스",
        "publish_year": "2026",
        "page": "190 p",
        "book_size": "188*257mm",
        "kdc": "005.58",
        "series_title": "모두의 시리즈",
        "series_no": "12",
        "field_sources": {"title": "nl.go.kr"},
    },
    "evidence": {
        "keywords": [{"word": "노션", "weight": 0.92}, {"word": "인공지능", "weight": 0.81}],
        "description": "노션과 노션 AI 활용법을 소개하는 입문서.",
        "co_loan_books": [],
        "title": "모두의 노션 AI",
        "author": "임대균 오가연 지음",
        "kdc_from_api": "005.58",
        "ddc_from_api": "",
        "translation_signals": {"detected": False, "hints": []},
        "available": {
            "keywords": True,
            "description": True,
            "co_loan_books": False,
            "translation_signals": False,
        },
    },
    "raw": {},
}

# 중간발표 결과에서 실제로 나왔던 형태의 LLM 출력.
LLM_OUTPUT = json.dumps(
    {
        "fields": [
            {
                "tag": "245",
                "source": "api",
                "indicator1": "1",
                "indicator2": "0",
                "subfields": [
                    {"code": "a", "value": "모두의 노션 AI"},
                    {"code": "c", "value": "임대균 오가연 지음"},
                ],
                "review_required": True,
                "confidence": "high",
            },
            {
                "tag": "546",
                "source": "ai_inference",
                "indicator1": " ",
                "indicator2": " ",
                "subfields": [{"code": "a", "value": "한국어로 된 자료"}],
                "review_required": True,
                "confidence": "medium",
                "evidence": {"from": ["title"], "reasoning": "표제가 한국어"},
            },
            {
                "tag": "653",
                "source": "ai_inference",
                "indicator1": " ",
                "indicator2": " ",
                "subfields": [
                    {"code": "a", "value": "인공지능"},
                    {"code": "a", "value": "업무관리"},
                ],
                "review_required": True,
                "confidence": "medium",
                "evidence": {
                    "from": ["keywords"],
                    "keywords_used": ["노션(0.92)", "인공지능(0.81)"],
                    "reasoning": "키워드 기반 주제 접근어",
                },
            },
        ],
        "skipped_fields": [],
        "warnings": [],
    },
    ensure_ascii=False,
)


class GeneratePipelineTests(unittest.TestCase):
    def _generate(self) -> dict[str, Any]:
        with patch(
            "backend.routers.generate.lookup_one", new=AsyncMock(return_value=LOOKUP_RESULT)
        ), patch("backend.clients.llm_client.generate", new=AsyncMock(return_value=LLM_OUTPUT)):
            with TestClient(app) as client:
                response = client.post("/api/generate/marc", json={"isbn": "9791194630678"})

        self.assertEqual(response.status_code, 200)
        return response.json()

    def _field(self, payload: dict[str, Any], tag: str) -> dict[str, Any]:
        matches = [field for field in payload["fields"] if field["tag"] == tag]
        self.assertEqual(len(matches), 1, f"{tag} 필드가 1개여야 합니다")
        return matches[0]

    def test_rule_layer_replaces_llm_title(self) -> None:
        payload = self._generate()
        field = self._field(payload, "245")

        self.assertEqual(field["generated_by"], "rule")
        self.assertEqual(
            [(sub["code"], sub["value"]) for sub in field["subfields"]],
            [
                ("a", "모두의 노션 AI"),
                ("b", "초보자도 바로 써먹는 노션 입문서"),
                ("d", "임대균 오가연 지음"),
            ],
        )

    def test_physical_description_converts_api_values(self) -> None:
        payload = self._generate()
        field = self._field(payload, "300")

        # 188*257mm → 세로 257mm → 26 cm
        self.assertEqual(
            [(sub["code"], sub["value"]) for sub in field["subfields"]],
            [("a", "190 p."), ("c", "26 cm")],
        )

    def test_api_fields_are_rule_generated(self) -> None:
        payload = self._generate()

        generated_by = {field["tag"]: field["generated_by"] for field in payload["fields"]}
        for tag in ("020", "245", "260", "300", "490", "056"):
            self.assertEqual(generated_by[tag], "rule", f"{tag}은 규칙 레이어가 만들어야 합니다")
        self.assertEqual(generated_by["653"], "llm")

    def test_unsupported_language_note_is_dropped(self) -> None:
        payload = self._generate()

        self.assertNotIn("546", {field["tag"] for field in payload["fields"]})
        skipped = {item["tag"]: item["reason"] for item in payload["skipped_fields"]}
        self.assertIn("546", skipped)
        self.assertIn("단일 언어 추정", skipped["546"])

    def test_missing_api_values_are_skipped_not_invented(self) -> None:
        payload = self._generate()

        skipped = {item["tag"] for item in payload["skipped_fields"]}
        self.assertIn("250", skipped)
        self.assertIn("082", skipped)
        self.assertNotIn("250", {field["tag"] for field in payload["fields"]})
        self.assertNotIn("082", {field["tag"] for field in payload["fields"]})


if __name__ == "__main__":
    unittest.main()
