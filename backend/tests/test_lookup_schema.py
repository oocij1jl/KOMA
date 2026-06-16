import unittest
from unittest.mock import AsyncMock, patch

from backend.schemas.lookup import BiblioSchema, LookupResponseSchema
from backend.services.evidence_service import merge_evidence
from backend.services.lookup_service import merge_biblio
from fastapi.testclient import TestClient

from backend.main import app


class LookupSchemaTests(unittest.TestCase):
    def test_merge_biblio_keeps_empty_values_as_blank_strings(self) -> None:
        biblio = merge_biblio(
            {
                "found": True,
                "title": "예시 제목",
                "author": "예시 저자",
                "publisher": "예시 출판사",
                "publish_predate": "20241231",
                "isbn": "9791194160004",
                "price": "₩17000",
            },
            {
                "found": False,
            },
        )

        validated = BiblioSchema.model_validate(biblio)
        self.assertEqual(validated.title, "예시 제목")
        self.assertEqual(validated.publisher, "예시 출판사")
        self.assertEqual(validated.pub_place, "")
        self.assertEqual(validated.kdc_edition, "")
        self.assertEqual(validated.field_sources["title"], "nl")

    def test_merge_biblio_ignores_short_publish_predate_for_year(self) -> None:
        biblio = merge_biblio(
            {
                "found": True,
                "publish_predate": "202",
            },
            {
                "found": False,
            },
        )

        validated = BiblioSchema.model_validate(biblio)
        self.assertEqual(validated.publish_year, "")
        self.assertEqual(validated.publish_predate, "202")

    def test_merge_evidence_includes_translation_signals_and_available(self) -> None:
        biblio = {
            "title": "예시 제목",
            "author": "홍길동 옮김",
            "description": "번역서 소개",
            "kdc": "001",
            "ddc": "100",
        }
        evidence = merge_evidence(
            biblio,
            {"keywords": [{"word": "도서관", "weight": 0.9}]},
            {"co_loan_books": [{"bookname": "관련 도서", "isbn13": "9780000000000", "authors": "저자"}]},
        )

        response = LookupResponseSchema.model_validate(
            {
                "isbn": "9791194160004",
                "biblio": {
                    "found": True,
                    "isbn_ea": "9791194160004",
                    "field_sources": {},
                },
                "evidence": evidence,
                "raw": {"nl": {}, "d4l_detail": {}, "d4l_keyword": {}, "d4l_usage": {}},
            }
        )

        self.assertTrue(response.evidence.translation_signals.detected)
        self.assertTrue(response.evidence.available.keywords)
        self.assertTrue(response.evidence.available.description)
        self.assertTrue(response.evidence.available.co_loan_books)
        self.assertTrue(response.evidence.available.translation_signals)
        self.assertEqual(response.evidence.keywords[0].word, "도서관")

    def test_single_lookup_endpoint_preserves_contract_shape(self) -> None:
        payload = {
            "isbn": "9780306406157",
            "biblio": {
                "found": True,
                "isbn_ea": "9780306406157",
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
            "found": True,
        }

        with patch("backend.routers.lookup.lookup_one", new=AsyncMock(return_value=payload)):
            client = TestClient(app)
            response = client.get("/api/lookup/isbn", params={"isbn": "9780306406157"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body.keys()), {"isbn", "biblio", "evidence", "raw"})
        self.assertNotIn("found", body)

    def test_single_lookup_404_uses_transformed_isbn_in_message(self) -> None:
        payload = {
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

        with patch("backend.routers.lookup.lookup_one", new=AsyncMock(return_value=payload)):
            client = TestClient(app)
            response = client.get("/api/lookup/isbn", params={"isbn": "89-364-3412-X"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "ISBN 9788936434120 에 해당하는 서지정보를 찾을 수 없습니다.")

    def test_bulk_lookup_endpoint_uses_biblio_found_without_top_level_found(self) -> None:
        payload = {
            "isbn": "9780306406157",
            "biblio": {
                "found": True,
                "isbn_ea": "9780306406157",
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
            "found": True,
        }

        with patch("backend.routers.lookup.lookup_one", new=AsyncMock(return_value=payload)):
            client = TestClient(app)
            response = client.post(
                "/api/lookup/isbn/bulk",
                json={"isbns": ["9780306406157"]},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(set(body["results"][0].keys()), {"isbn", "biblio", "evidence", "raw"})
        self.assertNotIn("found", body["results"][0])
        self.assertTrue(body["results"][0]["biblio"]["found"])

    def test_single_lookup_rejects_invalid_isbn13_checksum(self) -> None:
        client = TestClient(app)
        response = client.get("/api/lookup/isbn", params={"isbn": "9788936434121"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("ISBN-13 체크섬 오류", response.json()["detail"])

    def test_bulk_lookup_rejects_invalid_isbn13_checksum(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/api/lookup/isbn/bulk",
            json={"isbns": ["9788936434121"]},
        )

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["message"], "유효하지 않은 ISBN이 포함되어 있습니다.")
        self.assertIn("ISBN-13 체크섬 오류", detail["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()
