import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from backend.clients import nl_client

FAKE_NL_KEY = "FAKE-NL-CERTKEY-xyz789"


def _mock_transport_client(status_code: int, body: str = "error body") -> httpx.AsyncClient:
    """항상 주어진 status_code로 응답하는 실제 httpx.AsyncClient (진짜 HTTPStatusError를 만든다)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class RequestErrorWithSecretMessage(Exception):
    """URL/키가 메시지에 섞여 나올 수 있는 네트워크 오류를 흉내내는 테스트용 예외."""


class NlClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_nl_isbn_5xx_does_not_leak_key_in_error_or_log(self) -> None:
        client = _mock_transport_client(500, body="internal error")

        with patch.object(nl_client.settings, "NL_API_KEY", FAKE_NL_KEY):
            with self.assertLogs(nl_client.logger, level="WARNING") as captured:
                result = await nl_client.fetch_nl_isbn(client, "9788936434595")

        self.assertEqual(result["error"], "HTTP 500")
        self.assertNotIn(FAKE_NL_KEY, result["error"])
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_NL_KEY, log_text)
        self.assertIn("500", log_text)

    async def test_fetch_nl_isbn_network_error_does_not_leak_secret_message(self) -> None:
        client = Mock()
        secret_url = f"https://www.nl.go.kr/seoji/SearchApi.do?cert_key={FAKE_NL_KEY}&isbn=9788936434595"
        client.get = AsyncMock(side_effect=RequestErrorWithSecretMessage(f"connection failed for {secret_url}"))

        with patch.object(nl_client.settings, "NL_API_KEY", FAKE_NL_KEY):
            with self.assertLogs(nl_client.logger, level="WARNING") as captured:
                result = await nl_client.fetch_nl_isbn(client, "9788936434595")

        self.assertEqual(result["error"], "upstream request failed")
        self.assertNotIn(FAKE_NL_KEY, result["error"])
        self.assertNotIn(secret_url, result["error"])
        log_text = "\n".join(captured.output)
        self.assertNotIn(FAKE_NL_KEY, log_text)
        self.assertNotIn(secret_url, log_text)
        self.assertIn("RequestErrorWithSecretMessage", log_text)


if __name__ == "__main__":
    unittest.main()
