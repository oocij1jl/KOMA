"""backend/main.py의 lifespan 기반 httpx.AsyncClient 생성/재사용/종료 회귀 테스트.

이 테스트는 외부 API나 실제 인증정보(NL_API_KEY, D4L_API_KEY, OPENAI_API_KEY)에
의존하지 않는다. 검증 대상은 오직 "client 객체의 생성/재사용/종료 시점"이며,
실제 국중도/정보나루/OpenAI 네트워크 호출이나 조회 결과의 정확성은 다루지 않는다.
그래서 항상 핸들러 초입의 ISBN 형식 검증에서 422로 실패하는 값("invalid")을 써서
lookup_one()이 호출되기 전에 응답이 끝나도록 한다. FastAPI는 Depends(get_http_client)를
경로 파라미터 검증과 함께 핸들러 실행 전에 해석하므로, 이 422 응답도 dependency는
정상적으로 거쳐간다.

client 식별은 backend.clients.http_client.get_http_client를
app.dependency_overrides로 감싸 request.state.http_client를 캡처하는 방식으로
수행한다 (client 교체가 아니라 관찰용 오버라이드이며, 실제로 반환하는 값은 원래와 동일).
"""

from __future__ import annotations

import unittest
from collections.abc import Awaitable, Callable

import httpx
from fastapi import Request
from fastapi.testclient import TestClient

from backend.clients.http_client import get_http_client
from backend.main import app

INVALID_ISBN_PARAMS = {"isbn": "invalid"}


def _capturing_override(
    sink: list[httpx.AsyncClient],
) -> Callable[[Request], Awaitable[httpx.AsyncClient]]:
    """request.state.http_client를 그대로 반환하면서 sink에 기록만 하는 오버라이드."""

    async def _override(request: Request) -> httpx.AsyncClient:
        client = request.state.http_client
        sink.append(client)
        return client

    return _override


class HttpClientLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seen: list[httpx.AsyncClient] = []
        app.dependency_overrides[get_http_client] = _capturing_override(self.seen)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_http_client, None)

    def test_requests_within_same_lifespan_share_one_client(self) -> None:
        """1. 같은 lifespan의 여러 요청이 동일한 HTTP client를 사용한다."""
        with TestClient(app) as client:
            client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
            client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)

        self.assertEqual(len(self.seen), 2)
        self.assertIs(self.seen[0], self.seen[1])

    def test_client_closes_when_lifespan_shuts_down(self) -> None:
        """2. lifespan 종료 후 해당 client가 닫힌다."""
        with TestClient(app) as client:
            client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
            used_client = self.seen[-1]
            self.assertFalse(used_client.is_closed)

        self.assertTrue(used_client.is_closed)

    def test_next_lifespan_creates_a_different_client(self) -> None:
        """3. 다음 lifespan에서는 이전과 다른 client가 생성된다."""
        with TestClient(app) as client:
            client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
        first_client = self.seen[-1]

        with TestClient(app) as client:
            client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
        second_client = self.seen[-1]

        self.assertIsNot(first_client, second_client)
        self.assertTrue(first_client.is_closed)

    def test_overlapping_testclient_contexts_use_different_clients(self) -> None:
        """4. 같은 app의 두 TestClient context가 겹쳐도 각각 다른 client를 사용한다."""
        with TestClient(app) as outer_client:
            outer_client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
            captured_outer = self.seen[-1]

            with TestClient(app) as inner_client:
                inner_client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
                captured_inner = self.seen[-1]

            self.assertIsNot(captured_outer, captured_inner)

    def test_outer_client_stays_open_and_usable_after_inner_closes(self) -> None:
        """5. 안쪽 TestClient 종료 후에도 바깥쪽 client는 열려 있고 요청 처리가 가능하다."""
        with TestClient(app) as outer_client:
            outer_client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
            captured_outer = self.seen[-1]

            with TestClient(app) as inner_client:
                inner_client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
                captured_inner = self.seen[-1]

            self.assertTrue(captured_inner.is_closed)
            self.assertFalse(captured_outer.is_closed)

            response = outer_client.get("/api/lookup/isbn", params=INVALID_ISBN_PARAMS)
            self.assertEqual(response.status_code, 422)
            self.assertIs(self.seen[-1], captured_outer)


if __name__ == "__main__":
    unittest.main()
