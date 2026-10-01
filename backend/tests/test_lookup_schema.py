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

    def test_subtitle_is_split_from_detail_page_statement_by_api_title(self) -> None:
        biblio = merge_biblio(
            {"found": True, "title": "카프카의 문장들"},
            {"found": False},
            {"found": True, "title_statement": "카프카의 문장들 - 희박한 희망을 채굴하다"},
        )

        validated = BiblioSchema.model_validate(biblio)
        self.assertEqual(validated.subtitle, "희박한 희망을 채굴하다")
        self.assertEqual(validated.field_sources["subtitle"], "nl_seoji_detail")

    def test_subtitle_is_empty_when_statement_does_not_extend_api_title(self) -> None:
        for statement in ("카프카의 문장들", "다른 책 - 부제", "카프카의 문장들, 부제"):
            with self.subTest(statement=statement):
                biblio = merge_biblio(
                    {"found": True, "title": "카프카의 문장들"},
                    {"found": False},
                    {"found": True, "title_statement": statement},
                )

                self.assertEqual(BiblioSchema.model_validate(biblio).subtitle, "")

    def test_missing_detail_page_leaves_subtitle_empty(self) -> None:
        biblio = merge_biblio({"found": True, "title": "카프카의 문장들"}, {"found": False})

        self.assertEqual(BiblioSchema.model_validate(biblio).subtitle, "")

    def test_subtitle_prefers_aladin_api_over_pages(self) -> None:
        biblio = merge_biblio(
            {"found": True, "title": "카프카의 문장들"},
            {"found": False},
            {"found": True, "title_statement": "카프카의 문장들 - 상세 페이지 부제"},
            {"found": True, "subtitle": "알라딘 부제"},
            {"found": True, "subtitle": "교보 부제"},
        )

        validated = BiblioSchema.model_validate(biblio)
        self.assertEqual(validated.subtitle, "알라딘 부제")
        self.assertEqual(validated.field_sources["subtitle"], "aladin")

    def test_subtitle_falls_back_to_kyobo_when_api_and_page_are_empty(self) -> None:
        biblio = merge_biblio(
            {"found": True, "title": "카프카의 문장들"},
            {"found": False},
            {"found": False, "title_statement": ""},
            {"found": False},
            {"found": True, "subtitle": "교보 부제"},
        )

        validated = BiblioSchema.model_validate(biblio)
        self.assertEqual(validated.subtitle, "교보 부제")
        self.assertEqual(validated.field_sources["subtitle"], "kyobo")

    def test_subtitle_drops_responsibility_statement_after_colon(self) -> None:
        biblio = merge_biblio(
            {"found": True, "title": "처단"},
            {"found": False},
            {"found": True, "title_statement": "처단 - 그날 계엄을 막지 못했더라면 :정보라 소설"},
        )

        self.assertEqual(BiblioSchema.model_validate(biblio).subtitle, "그날 계엄을 막지 못했더라면")

    def test_parallel_title_separator_is_not_treated_as_subtitle(self) -> None:
        biblio = merge_biblio(
            {"found": True, "title": "민강"},
            {"found": False},
            {"found": True, "title_statement": "민강 = Min Kang"},
        )

        self.assertEqual(BiblioSchema.model_validate(biblio).subtitle, "")

    def test_aladin_page_and_size_fill_only_when_nl_is_missing(self) -> None:
        aladin = {"found": True, "item_page": "399", "size_width_mm": "120", "size_height_mm": "192"}
        filled = BiblioSchema.model_validate(
            merge_biblio({"found": True}, {"found": False}, None, aladin)
        )
        self.assertEqual((filled.page, filled.book_size), ("399 p.", "120*192mm"))
        self.assertEqual(filled.field_sources["page"], "aladin")

        kept = BiblioSchema.model_validate(
            merge_biblio({"found": True, "page": "400 p.", "book_size": "188*257mm"}, {"found": False}, None, aladin)
        )
        self.assertEqual((kept.page, kept.book_size), ("400 p.", "188*257mm"))
        self.assertEqual(kept.field_sources["page"], "nl")

    def test_page_prefers_kyobo_and_falls_back_to_nl(self) -> None:
        kyobo = {"found": True, "page": "400 p.", "book_size": "128*197mm", "subtitle": ""}
        preferred = BiblioSchema.model_validate(
            merge_biblio({"found": True, "page": "399 p.", "book_size": "120*192"}, {"found": False}, None, None, kyobo)
        )
        self.assertEqual(preferred.page, "400 p.")
        self.assertEqual(preferred.field_sources["page"], "kyobo")
        # 크기는 국중도 값을 유지한다. 교보 수치에는 두께가 섞여 있어 보조로만 쓴다.
        self.assertEqual(preferred.book_size, "120*192")

        without_kyobo = BiblioSchema.model_validate(
            merge_biblio({"found": True, "page": "399 p."}, {"found": False}, None, None, {"found": False})
        )
        self.assertEqual(without_kyobo.page, "399 p.")
        self.assertEqual(without_kyobo.field_sources["page"], "nl")

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

        with patch("backend.routers.lookup.lookup_one", new=AsyncMock(return_value=payload)), TestClient(
            app
        ) as client:
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

        with patch("backend.routers.lookup.lookup_one", new=AsyncMock(return_value=payload)), TestClient(
            app
        ) as client:
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

        with patch("backend.routers.lookup.lookup_one", new=AsyncMock(return_value=payload)), TestClient(
            app
        ) as client:
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
        with TestClient(app) as client:
            response = client.get("/api/lookup/isbn", params={"isbn": "9788936434121"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("ISBN-13 체크섬 오류", response.json()["detail"])

    def test_bulk_lookup_rejects_invalid_isbn13_checksum(self) -> None:
        with TestClient(app) as client:
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
