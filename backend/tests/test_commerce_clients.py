"""알라딘 상품 API·교보문고 상세 수집 클라이언트 테스트.

실제 네트워크와 실제 인증키를 쓰지 않는다. httpx.MockTransport로 응답을 만들어
정규화 결과와 실패 처리(키 없음, HTTP 오류, 구조 변경)를 확인한다.
"""

import json
import unittest
import unittest.mock

import httpx

from backend.clients import aladin_client, kyobo_client

ALADIN_ITEM = {
    "item": [
        {
            "title": "카프카의 문장들",
            "author": "프란츠 카프카 지음",
            "publisher": "아날로그",
            "isbn13": "9788960909830",
            "description": "책소개",
            "subInfo": {
                "subTitle": "희박한 희망을 채굴하다",
                "originalTitle": "Kafka",
                "itemPage": 399,
                "packing": {"styleDesc": "양장본", "sizeWidth": 120, "sizeHeight": 192},
            },
        }
    ]
}

KYOBO_DETAIL = (
    '<h1 class="fz-28" aria-label="카프카의 문장들"><span>카프카의 문장들</span></h1>'
    '<p class="line-clamp-2" aria-label="희박한 희망을 채굴하다 | 양장본 Hardcover">'
    '<span>희박한 희망을 채굴하다</span></p></div>'
    '<table aria-label="상품정보"><caption>상품정보 테이블로 ISBN, 쪽수/크기를 나타낸 표입니다.</caption>'
    '<tbody><tr><th scope="row">ISBN</th><td><div>9788960909830</div></td></tr>'
    '<tr><th scope="row">쪽수/크기</th><td><div>400쪽 | 128 * 197 * 34 mm / 573 g</div></td></tr>'
    '<tr><th scope="row">원서(번역서)명/저자명</th><td><div>Kafka / Franz Kafka</div></td></tr>'
    "</tbody></table>"
)


class AladinClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_item_lookup_normalizes_subtitle_page_and_size(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.params.get("itemIdType"), "ISBN13")
            self.assertEqual(request.url.params.get("ItemId"), "9788960909830")
            return httpx.Response(200, text=json.dumps(ALADIN_ITEM))

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with unittest.mock.patch.object(aladin_client.settings, "ALADIN_TTB_KEY", "ttbtest"):
            result = await aladin_client.fetch_aladin_item(client, "9788960909830")

        self.assertTrue(result["found"])
        self.assertEqual(result["subtitle"], "희박한 희망을 채굴하다")
        self.assertEqual(result["original_title"], "Kafka")
        self.assertEqual(result["item_page"], "399")
        self.assertEqual((result["size_width_mm"], result["size_height_mm"]), ("120", "192"))

    async def test_missing_key_skips_call(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
            raise AssertionError("키가 없으면 호출하지 않아야 한다")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with unittest.mock.patch.object(aladin_client.settings, "ALADIN_TTB_KEY", ""):
            result = await aladin_client.fetch_aladin_item(client, "9788960909830")

        self.assertFalse(result["found"])
        self.assertIn("ALADIN_TTB_KEY", result["error"])

    async def test_error_response_and_http_failure_do_not_raise(self) -> None:
        error_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text=json.dumps({"errorCode": 1, "errorMessage": "잘못된 키"}))
            )
        )
        failing_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(500, text="error"))
        )

        with unittest.mock.patch.object(aladin_client.settings, "ALADIN_TTB_KEY", "ttbtest"):
            error_result = await aladin_client.fetch_aladin_item(error_client, "9788960909830")
            failed_result = await aladin_client.fetch_aladin_item(failing_client, "9788960909830")

        self.assertEqual(error_result["error"], "잘못된 키")
        self.assertEqual(failed_result["error"], "HTTP 500")


class KyoboClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_then_detail_returns_title_and_subtitle(self) -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if "search" in str(request.url):
                return httpx.Response(
                    200, text='<a href="https://product.kyobobook.co.kr/detail/S000219519013">책</a>'
                )
            self.assertEqual(request.headers["Referer"], "https://search.kyobobook.co.kr/")
            return httpx.Response(200, text=KYOBO_DETAIL)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await kyobo_client.fetch_kyobo_detail(client, "9788960909830")

        self.assertTrue(result["found"])
        self.assertEqual(result["title"], "카프카의 문장들")
        self.assertEqual(result["subtitle"], "희박한 희망을 채굴하다")
        self.assertEqual(result["page"], "400 p.")
        self.assertEqual(result["book_size"], "128*197mm")
        self.assertEqual(result["original_title"], "Kafka / Franz Kafka")
        self.assertEqual(len(requested), 2)

    async def test_detail_without_subtitle_paragraph_returns_blank_subtitle(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if "search" in str(request.url):
                return httpx.Response(200, text="https://product.kyobobook.co.kr/detail/S000000000001")
            return httpx.Response(200, text='<h1 aria-label="민강"><span>민강</span></h1></div>')

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await kyobo_client.fetch_kyobo_detail(client, "9791175610729")

        self.assertTrue(result["found"])
        self.assertEqual(result["subtitle"], "")
        self.assertEqual((result["page"], result["book_size"]), ("", ""))

    async def test_missing_product_link_is_reported_as_not_found(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="검색 결과 없음"))
        )

        result = await kyobo_client.fetch_kyobo_detail(client, "9788960909830")

        self.assertFalse(result["found"])
        self.assertEqual(result["subtitle"], "")


if __name__ == "__main__":
    unittest.main()
