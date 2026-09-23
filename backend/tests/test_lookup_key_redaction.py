"""정보나루 키워드/이용분석 API가 HTTP 오류를 반환할 때, 실제 authKey가
앱 WARNING 로그나 /api/lookup/isbn/bulk 응답(raw)에 노출되지 않는지 확인하는
엔드투엔드 회귀 테스트.

실제 네트워크·실제 API 키를 쓰지 않는다. 대신 httpx.MockTransport로 진짜
httpx.Response/HTTPStatusError를 만들어, raise_for_status() 이후의 처리
경로(로그 기록 + 응답 필드 구성)가 실제로 안전한지 검증한다.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.clients.http_client import get_http_client
from backend.config import settings
from backend.main import app

FAKE_D4L_KEY = "FAKE-D4L-AUTHKEY-bulk-test"
FAKE_NL_KEY = "FAKE-NL-CERTKEY-bulk-test"


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "SearchApi.do" in url:  # 국립중앙도서관 — 이번 버그와 무관, 정상 응답
        return httpx.Response(200, json={"docs": []})
    if "srchDtlList" in url:  # 정보나루 상세조회 — 이번 버그와 무관, 정상 응답
        return httpx.Response(200, json={"response": {"detail": []}})
    if "keywordList" in url:  # 정보나루 키워드 — 5xx 오류 재현
        return httpx.Response(500, text="internal server error")
    if "usageAnalysisList" in url:  # 정보나루 이용분석 — 4xx 오류 재현
        return httpx.Response(429, text="rate limited")
    raise AssertionError(f"unexpected URL in test transport: {url}")


def _override_with(mock_client: httpx.AsyncClient):
    def _override() -> httpx.AsyncClient:
        return mock_client

    return _override


class LookupBulkKeyRedactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        app.dependency_overrides[get_http_client] = _override_with(self.mock_client)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_http_client, None)

    def test_bulk_lookup_keeps_key_out_of_response_and_logs_on_upstream_errors(self) -> None:
        with patch.object(settings, "D4L_API_KEY", FAKE_D4L_KEY), patch.object(
            settings, "NL_API_KEY", FAKE_NL_KEY
        ):
            with self.assertLogs(level="WARNING") as captured:
                with TestClient(app) as client:
                    response = client.post(
                        "/api/lookup/isbn/bulk",
                        json={"isbns": ["9788936434595"]},
                    )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        result = body["results"][0]

        # 안전한 진단 정보(상태 코드)는 남아 있어야 한다.
        self.assertEqual(result["raw"]["d4l_keyword"]["error"], "HTTP 500")
        self.assertEqual(result["raw"]["d4l_usage"]["error"], "HTTP 429")

        # 응답 본문 전체 어디에도 가짜 키가 없어야 한다.
        body_text = json.dumps(body, ensure_ascii=False)
        self.assertNotIn(FAKE_D4L_KEY, body_text)
        self.assertNotIn(FAKE_NL_KEY, body_text)

        # 캡처된 WARNING 로그 어디에도 가짜 키가 없어야 한다.
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_D4L_KEY, log_text)
        self.assertNotIn(FAKE_NL_KEY, log_text)
        # 로그에는 진단 가능한 정보(상태 코드)는 남아 있어야 한다.
        self.assertIn("500", log_text)
        self.assertIn("429", log_text)


if __name__ == "__main__":
    unittest.main()
