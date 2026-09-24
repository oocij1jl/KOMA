import asyncio
import threading
import unittest
from typing import cast
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from backend.clients.llm_client import LLMClientError
from backend.config import settings
from backend.main import app
from backend.routers import generate as generate_router
from backend.schemas.llm_output import GenerateResult
from backend.schemas.lookup import LookupResponseSchema
from backend.services.llm_input_builder import build_llm_input
from backend.services.lookup_service import lookup_one
from backend.services.output_validator import OutputValidationError


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
            "MVP 기본 skip — 통제 주제명은 표목표 대조 필요: 653으로 대체",
        )
        self.assertEqual(generate_options["review_required_fields"], ["653", "056", "082"])
        self.assertEqual(generate_options["skipped_by_default"], ["650", "830", "950"])
        self.assertNotIn("650", generate_options["required_fields"])
        self.assertNotIn("650", generate_options["review_required_fields"])
        # 710 단체저자는 근거가 있을 때만 만드는 조건부 필드다.
        self.assertIn("710", generate_options["conditional_fields"])

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

    def test_lookup_one_skips_d4l_usage_call_when_flag_enabled(self) -> None:
        """D4L_SKIP_USAGE=True면 이용분석(co_loan_books) 호출을 건너뛰고,
        keywords/description 근거는 그대로 유지되어야 한다 (정보나루 일일
        호출 한도 절약용)."""

        async def run_test() -> None:
            with patch(
                "backend.services.lookup_service.fetch_nl_isbn",
                new=AsyncMock(return_value={"source": "nl.go.kr", "found": True, "isbn": "9788936434120"}),
            ), patch(
                "backend.services.lookup_service.fetch_d4l_detail",
                new=AsyncMock(
                    return_value={
                        "source": "data4library.kr",
                        "found": True,
                        "isbn13": "9788936434120",
                        "description": "설명",
                    }
                ),
            ), patch(
                "backend.services.lookup_service.fetch_d4l_keywords",
                new=AsyncMock(
                    return_value={
                        "source": "keywordList",
                        "found": True,
                        "keywords": [{"word": "테스트", "weight": 1.0}],
                    }
                ),
            ), patch(
                "backend.services.lookup_service.fetch_d4l_usage", new=AsyncMock()
            ) as usage_mock, patch.object(settings, "D4L_SKIP_USAGE", True):
                async with httpx.AsyncClient() as client:
                    result = await lookup_one(client, "89-364-3412-X")

                usage_mock.assert_not_called()
                self.assertEqual(result["raw"]["d4l_usage"]["co_loan_books"], [])
                self.assertEqual(result["evidence"]["co_loan_books"], [])
                # 이용분석은 빠져도 키워드/description 근거는 그대로 유지되어야 한다
                self.assertEqual(result["evidence"]["keywords"], [{"word": "테스트", "weight": 1.0}])
                self.assertEqual(result["evidence"]["description"], "설명")

        asyncio.run(run_test())

    def test_generate_routes_return_generate_result_with_primary_and_alias(self) -> None:
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

        generated = GenerateResult.model_validate(
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
                        "evidence": {
                            "from": ["keywords"],
                            "keywords_used": ["채식주의(0.91)"],
                            "reasoning": "키워드 근거",
                        },
                    }
                ],
                "skipped_fields": [{"tag": "650", "reason": "통제 주제명은 표목표 대조 필요: 653으로 대체"}],
                "warnings": ["653 색인어는 키워드 기반 추론 — 반드시 검수"],
            }
        )

        with patch("backend.routers.generate.lookup_one", new=AsyncMock(return_value=lookup_payload)), patch(
            "backend.routers.generate.generate_marc_result",
            new=AsyncMock(return_value=generated),
        ) as generate_mock, TestClient(app) as client:
            primary = client.post("/api/generate/marc", json={"isbn": "89-364-3412-X"})
            alias = client.post("/api/generate", json={"isbn": "89-364-3412-X"})

        self.assertEqual(primary.status_code, 200)
        self.assertEqual(alias.status_code, 200)
        self.assertTrue(primary.headers["content-type"].startswith("application/json"))
        self.assertTrue(alias.headers["content-type"].startswith("application/json"))
        self.assertEqual(primary.json(), alias.json())
        generate_mock.assert_awaited()

        body = primary.json()
        self.assertEqual(body["fields"][0]["tag"], "653")
        self.assertEqual(body["fields"][0]["evidence"]["from"], ["keywords"])
        self.assertEqual(body["skipped_fields"][0]["tag"], "650")

    def test_generate_routes_return_generate_result_even_with_partial_evidence(self) -> None:
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

        generated = GenerateResult.model_validate(
            {
                "fields": [],
                "skipped_fields": [
                    {"tag": "653", "reason": "근거 부족"},
                    {"tag": "650", "reason": "통제 주제명은 표목표 대조 필요: 653으로 대체"},
                ],
                "warnings": [],
            }
        )

        with patch("backend.routers.generate.lookup_one", new=AsyncMock(return_value=lookup_payload)), patch(
            "backend.routers.generate.generate_marc_result",
            new=AsyncMock(return_value=generated),
        ), TestClient(app) as client:
            response = client.post("/api/generate/marc", json={"isbn": "89-364-3412-X"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("application/json"))
        response_json = response.json()
        self.assertEqual(response_json["fields"], [])
        self.assertEqual(response_json["skipped_fields"][0]["tag"], "653")

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

        with patch("backend.routers.generate.lookup_one", new=AsyncMock(return_value=lookup_payload)), TestClient(
            app
        ) as client:
            response = client.post("/api/generate/marc", json={"isbn": "89-364-3412-X"})

        self.assertEqual(response.status_code, 404)
        response_json = cast(dict[str, object], response.json())
        detail = response_json["detail"]
        if not isinstance(detail, str):
            self.fail("detail should be a string")
        self.assertIn("ISBN 9788936434120", detail)

    def test_generate_routes_return_422_for_invalid_isbn(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/generate/marc", json={"isbn": "abc"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "유효하지 않은 ISBN 형식: 'abc'")

    def test_generate_routes_return_422_for_invalid_isbn13_checksum(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/generate/marc", json={"isbn": "9788936434121"})

        self.assertEqual(response.status_code, 422)
        response_json = cast(dict[str, object], response.json())
        detail = response_json["detail"]
        if not isinstance(detail, str):
            self.fail("detail should be a string")
        self.assertIn("ISBN-13 체크섬 오류", detail)


def _bulk_lookup_payload(isbn: str, *, found: bool = True) -> dict[str, object]:
    return {
        "isbn": isbn,
        "biblio": {
            "found": found,
            "isbn_ea": isbn if found else "",
            "title": "예시 제목" if found else "",
            "author": "예시 저자" if found else "",
            "field_sources": {},
        },
        "evidence": {
            "keywords": [],
            "description": "",
            "co_loan_books": [],
            "title": "예시 제목" if found else "",
            "author": "예시 저자" if found else "",
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
        "found": found,
    }


def _bulk_generated_result() -> GenerateResult:
    return GenerateResult.model_validate({"fields": [], "skipped_fields": [], "warnings": []})


class GenerateBulkTests(unittest.TestCase):
    def test_bulk_returns_mixed_success_and_error_results_without_failing_whole_request(self) -> None:
        lookup_payloads = {
            "9788936434120": _bulk_lookup_payload("9788936434120", found=True),
            "9791100000009": _bulk_lookup_payload("9791100000009", found=False),
        }

        async def lookup_side_effect(client: object, isbn: str) -> dict[str, object]:
            if isbn == "89-000-0000-0":
                raise ValueError("유효하지 않은 ISBN 형식: '89-000-0000-0'")
            return lookup_payloads[isbn]

        async def generate_side_effect(llm_input: object) -> GenerateResult:
            if getattr(llm_input, "isbn", None) == "9788936434120":
                return _bulk_generated_result()
            raise AssertionError("generate_marc_result should not be called for this isbn")

        with patch(
            "backend.routers.generate.lookup_one", new=AsyncMock(side_effect=lookup_side_effect)
        ), patch(
            "backend.routers.generate.generate_marc_result",
            new=AsyncMock(side_effect=generate_side_effect),
        ), TestClient(app) as client:
            response = client.post(
                "/api/generate/marc/bulk",
                json={"isbns": ["9788936434120", "9791100000009", "89-000-0000-0"]},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 3)
        results_by_isbn = {item["isbn"]: item for item in body["results"]}

        success = results_by_isbn["9788936434120"]
        self.assertEqual(success["status"], "success")
        self.assertEqual(success["result"]["fields"], [])

        not_found = results_by_isbn["9791100000009"]
        self.assertEqual(not_found["status"], "error")
        self.assertEqual(not_found["error_code"], "not_found")

        invalid = results_by_isbn["89-000-0000-0"]
        self.assertEqual(invalid["status"], "error")
        self.assertEqual(invalid["error_code"], "invalid_isbn")

    def test_bulk_reports_llm_error_and_validation_error_codes(self) -> None:
        lookup_payloads = {
            "9788936434120": _bulk_lookup_payload("9788936434120", found=True),
            "9791100000009": _bulk_lookup_payload("9791100000009", found=True),
        }

        async def lookup_side_effect(client: object, isbn: str) -> dict[str, object]:
            return lookup_payloads[isbn]

        async def generate_side_effect(llm_input: object) -> GenerateResult:
            if getattr(llm_input, "isbn", None) == "9788936434120":
                raise LLMClientError("LLM 호출 시간이 초과되었습니다.")
            raise OutputValidationError("LLM 응답은 JSON 객체여야 합니다.")

        with patch(
            "backend.routers.generate.lookup_one", new=AsyncMock(side_effect=lookup_side_effect)
        ), patch(
            "backend.routers.generate.generate_marc_result",
            new=AsyncMock(side_effect=generate_side_effect),
        ), TestClient(app) as client:
            response = client.post(
                "/api/generate/marc/bulk",
                json={"isbns": ["9788936434120", "9791100000009"]},
            )

        self.assertEqual(response.status_code, 200)
        results_by_isbn = {item["isbn"]: item for item in response.json()["results"]}
        self.assertEqual(results_by_isbn["9788936434120"]["error_code"], "llm_error")
        self.assertEqual(results_by_isbn["9791100000009"]["error_code"], "validation_error")

    def test_bulk_rejects_empty_isbn_list(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/generate/marc/bulk", json={"isbns": []})

        self.assertEqual(response.status_code, 422)

    def test_bulk_rejects_more_than_ten_isbns(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/generate/marc/bulk",
                json={"isbns": [f"978893643412{i}" for i in range(11)]},
            )

        self.assertEqual(response.status_code, 422)

    def test_bulk_limits_concurrent_generate_calls(self) -> None:
        isbns = [f"978893643412{i}" for i in range(5)]
        lookup_payloads = {isbn: _bulk_lookup_payload(isbn, found=True) for isbn in isbns}

        async def lookup_side_effect(client: object, isbn: str) -> dict[str, object]:
            return lookup_payloads[isbn]

        state = {"current": 0, "max_seen": 0}
        lock = asyncio.Lock()

        async def generate_side_effect(llm_input: object) -> GenerateResult:
            async with lock:
                state["current"] += 1
                state["max_seen"] = max(state["max_seen"], state["current"])
            await asyncio.sleep(0.05)
            async with lock:
                state["current"] -= 1
            return _bulk_generated_result()

        with patch(
            "backend.routers.generate.lookup_one", new=AsyncMock(side_effect=lookup_side_effect)
        ), patch(
            "backend.routers.generate.generate_marc_result",
            new=AsyncMock(side_effect=generate_side_effect),
        ), TestClient(app) as client:
            response = client.post("/api/generate/marc/bulk", json={"isbns": isbns})

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(state["max_seen"], 2)
        self.assertLessEqual(state["max_seen"], generate_router.GENERATE_BULK_CONCURRENCY)

    def test_bulk_concurrency_cap_is_shared_across_separate_requests(self) -> None:
        """대량 테스트에서 10건씩 여러 bulk 요청이 겹쳐 들어와도, 동시 LLM 호출 수는
        요청 수와 무관하게 GENERATE_BULK_CONCURRENCY 하나로 제한되어야 한다."""
        batch1 = [f"978893643412{i}" for i in range(3)]
        batch2 = [f"978893643413{i}" for i in range(3)]
        lookup_payloads = {isbn: _bulk_lookup_payload(isbn, found=True) for isbn in batch1 + batch2}

        async def lookup_side_effect(client: object, isbn: str) -> dict[str, object]:
            return lookup_payloads[isbn]

        state = {"current": 0, "max_seen": 0}
        lock = asyncio.Lock()

        async def generate_side_effect(llm_input: object) -> GenerateResult:
            async with lock:
                state["current"] += 1
                state["max_seen"] = max(state["max_seen"], state["current"])
            await asyncio.sleep(0.05)
            async with lock:
                state["current"] -= 1
            return _bulk_generated_result()

        responses: list[object] = []

        def call_bulk(isbns: list[str]) -> None:
            responses.append(client.post("/api/generate/marc/bulk", json={"isbns": isbns}))

        with patch(
            "backend.routers.generate.lookup_one", new=AsyncMock(side_effect=lookup_side_effect)
        ), patch(
            "backend.routers.generate.generate_marc_result",
            new=AsyncMock(side_effect=generate_side_effect),
        ), TestClient(app) as client:
            thread1 = threading.Thread(target=call_bulk, args=(batch1,))
            thread2 = threading.Thread(target=call_bulk, args=(batch2,))
            thread1.start()
            thread2.start()
            thread1.join()
            thread2.join()

        self.assertEqual(len(responses), 2)
        for response in responses:
            self.assertEqual(response.status_code, 200)  # type: ignore[attr-defined]
        self.assertGreaterEqual(state["max_seen"], 2)
        self.assertLessEqual(state["max_seen"], generate_router.GENERATE_BULK_CONCURRENCY)


if __name__ == "__main__":
    _ = unittest.main()
