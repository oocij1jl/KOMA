import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from backend.clients import data4library_client

FAKE_D4L_KEY = "FAKE-D4L-AUTHKEY-abc123"


def _mock_transport_client(status_code: int, body: str = "error body") -> httpx.AsyncClient:
    """항상 주어진 status_code로 응답하는 실제 httpx.AsyncClient (진짜 HTTPStatusError를 만든다)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class RequestErrorWithSecretMessage(Exception):
    """URL/키가 메시지에 섞여 나올 수 있는 네트워크 오류를 흉내내는 테스트용 예외."""


class Data4LibraryClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_d4l_detail_handles_empty_response_body(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = "   "
        response.json.side_effect = AssertionError("json() should not be called")

        client = Mock()
        client.get = AsyncMock(return_value=response)

        with patch.object(data4library_client.settings, "D4L_API_KEY", "dummy-key"):
            result = await data4library_client.fetch_d4l_detail(client, "9788936434595")

        self.assertFalse(result["found"])
        self.assertEqual(result["error"], "empty response from upstream")
        self.assertEqual(result["source"], "data4library.kr")

    async def test_fetch_d4l_keywords_handles_empty_response_body(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = ""
        response.json.side_effect = AssertionError("json() should not be called")

        client = Mock()
        client.get = AsyncMock(return_value=response)

        with patch.object(data4library_client.settings, "D4L_API_KEY", "dummy-key"):
            result = await data4library_client.fetch_d4l_keywords(client, "9788936434595")

        self.assertFalse(result["found"])
        self.assertEqual(result["keywords"], [])
        self.assertEqual(result["error"], "empty response from upstream")
        self.assertEqual(result["source"], "keywordList")

    async def test_fetch_d4l_usage_handles_empty_response_body(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = ""
        response.json.side_effect = AssertionError("json() should not be called")

        client = Mock()
        client.get = AsyncMock(return_value=response)

        with patch.object(data4library_client.settings, "D4L_API_KEY", "dummy-key"):
            result = await data4library_client.fetch_d4l_usage(client, "9788936434595")

        self.assertFalse(result["found"])
        self.assertEqual(result["co_loan_books"], [])
        self.assertEqual(result["error"], "empty response from upstream")
        self.assertEqual(result["source"], "usageAnalysisList")

    async def test_fetch_d4l_keywords_5xx_does_not_leak_key_in_error_or_log(self) -> None:
        client = _mock_transport_client(500, body="internal error")

        with patch.object(data4library_client.settings, "D4L_API_KEY", FAKE_D4L_KEY):
            with self.assertLogs(data4library_client.logger, level="WARNING") as captured:
                result = await data4library_client.fetch_d4l_keywords(client, "9788936434595")

        self.assertEqual(result["error"], "HTTP 500")
        self.assertNotIn(FAKE_D4L_KEY, result["error"])
        self.assertEqual(result["keywords"], [])
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_D4L_KEY, log_text)
        self.assertIn("500", log_text)

    async def test_fetch_d4l_keywords_4xx_does_not_leak_key_in_error_or_log(self) -> None:
        client = _mock_transport_client(429, body="rate limited")

        with patch.object(data4library_client.settings, "D4L_API_KEY", FAKE_D4L_KEY):
            with self.assertLogs(data4library_client.logger, level="WARNING") as captured:
                result = await data4library_client.fetch_d4l_keywords(client, "9788936434595")

        self.assertEqual(result["error"], "HTTP 429")
        self.assertNotIn(FAKE_D4L_KEY, result["error"])
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_D4L_KEY, log_text)

    async def test_fetch_d4l_usage_5xx_does_not_leak_key_in_error_or_log(self) -> None:
        client = _mock_transport_client(500, body="internal error")

        with patch.object(data4library_client.settings, "D4L_API_KEY", FAKE_D4L_KEY):
            with self.assertLogs(data4library_client.logger, level="WARNING") as captured:
                result = await data4library_client.fetch_d4l_usage(client, "9788936434595")

        self.assertEqual(result["error"], "HTTP 500")
        self.assertNotIn(FAKE_D4L_KEY, result["error"])
        self.assertEqual(result["co_loan_books"], [])
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_D4L_KEY, log_text)

    async def test_fetch_d4l_usage_4xx_does_not_leak_key_in_error_or_log(self) -> None:
        client = _mock_transport_client(403, body="forbidden")

        with patch.object(data4library_client.settings, "D4L_API_KEY", FAKE_D4L_KEY):
            with self.assertLogs(data4library_client.logger, level="WARNING") as captured:
                result = await data4library_client.fetch_d4l_usage(client, "9788936434595")

        self.assertEqual(result["error"], "HTTP 403")
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_D4L_KEY, log_text)

    async def test_fetch_d4l_keywords_network_error_does_not_leak_secret_message(self) -> None:
        client = Mock()
        secret_url = f"https://data4library.kr/api/keywordList?authKey={FAKE_D4L_KEY}&isbn13=9788936434595"
        client.get = AsyncMock(side_effect=RequestErrorWithSecretMessage(f"connection failed for {secret_url}"))

        with patch.object(data4library_client.settings, "D4L_API_KEY", FAKE_D4L_KEY):
            with self.assertLogs(data4library_client.logger, level="WARNING") as captured:
                result = await data4library_client.fetch_d4l_keywords(client, "9788936434595")

        self.assertEqual(result["error"], "upstream request failed")
        self.assertNotIn(FAKE_D4L_KEY, result["error"])
        self.assertNotIn(secret_url, result["error"])
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_D4L_KEY, log_text)
        self.assertNotIn(secret_url, log_text)
        self.assertIn("RequestErrorWithSecretMessage", log_text)

    async def test_fetch_d4l_usage_network_error_does_not_leak_secret_message(self) -> None:
        client = Mock()
        secret_url = f"https://data4library.kr/api/usageAnalysisList?authKey={FAKE_D4L_KEY}&isbn13=9788936434595"
        client.get = AsyncMock(side_effect=RequestErrorWithSecretMessage(f"connection failed for {secret_url}"))

        with patch.object(data4library_client.settings, "D4L_API_KEY", FAKE_D4L_KEY):
            with self.assertLogs(data4library_client.logger, level="WARNING") as captured:
                result = await data4library_client.fetch_d4l_usage(client, "9788936434595")

        self.assertEqual(result["error"], "upstream request failed")
        self.assertNotIn(FAKE_D4L_KEY, result["error"])
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_D4L_KEY, log_text)
        self.assertNotIn(secret_url, log_text)

    async def test_fetch_d4l_detail_network_error_does_not_leak_secret_message(self) -> None:
        client = Mock()
        secret_url = f"https://data4library.kr/api/srchDtlList?authKey={FAKE_D4L_KEY}&isbn13=9788936434595"
        client.get = AsyncMock(side_effect=RequestErrorWithSecretMessage(f"connection failed for {secret_url}"))

        with patch.object(data4library_client.settings, "D4L_API_KEY", FAKE_D4L_KEY):
            with self.assertLogs(data4library_client.logger, level="WARNING") as captured:
                result = await data4library_client.fetch_d4l_detail(client, "9788936434595")

        self.assertEqual(result["error"], "upstream request failed")
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_D4L_KEY, log_text)
        self.assertNotIn(secret_url, log_text)


if __name__ == "__main__":
    unittest.main()
