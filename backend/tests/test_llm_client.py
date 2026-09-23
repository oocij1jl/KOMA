import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.clients import llm_client


class MockResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", llm_client.OPENAI_CHAT_COMPLETIONS_URL)
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict[str, object]:
        return self._payload


class MockClient:
    def __init__(self) -> None:
        self.last_request: dict[str, object] | None = None

    async def post(self, url: str, **kwargs: object) -> MockResponse:
        self.last_request = {"url": url, **kwargs}
        return MockResponse({"choices": [{"message": {"content": '{"fields":[],"skipped_fields":[],"warnings":[]}'}}]})


class FlakyClient:
    """호출할 때마다 미리 정해둔 응답/예외를 순서대로 돌려주는 테스트용 클라이언트."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    async def post(self, url: str, **kwargs: object) -> MockResponse:
        self.call_count += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class LLMClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_uses_openai_json_mode(self) -> None:
        client = MockClient()
        with patch.object(llm_client.settings, "OPENAI_API_KEY", "test-key"), patch.object(
            llm_client.settings,
            "OPENAI_MODEL",
            "gpt-test",
        ):
            content = await llm_client.generate("prompt", client=client)  # type: ignore[arg-type]

        self.assertIn('"fields"', content)
        self.assertIsNotNone(client.last_request)
        request = client.last_request
        if request is None:
            self.fail("request should be recorded")
        self.assertEqual(request["url"], llm_client.OPENAI_CHAT_COMPLETIONS_URL)
        json_body = request["json"]
        if not isinstance(json_body, dict):
            self.fail("json body should be a dict")
        self.assertEqual(json_body["model"], "gpt-test")
        self.assertEqual(json_body["response_format"], {"type": "json_object"})
        headers = request["headers"]
        if not isinstance(headers, dict):
            self.fail("headers should be a dict")
        self.assertEqual(headers["Authorization"], "Bearer test-key")

    async def test_generate_requires_api_key(self) -> None:
        with patch.object(llm_client.settings, "OPENAI_API_KEY", ""):
            with self.assertRaises(llm_client.LLMClientError):
                _ = await llm_client.generate("prompt", client=MockClient())  # type: ignore[arg-type]

    async def test_generate_retries_once_on_5xx_then_succeeds(self) -> None:
        success = MockResponse(
            {"choices": [{"message": {"content": '{"fields":[],"skipped_fields":[],"warnings":[]}'}}]}
        )
        client = FlakyClient([MockResponse({}, status_code=500), success])
        with patch.object(llm_client.settings, "OPENAI_API_KEY", "test-key"), patch(
            "backend.clients.llm_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            content = await llm_client.generate("prompt", client=client)  # type: ignore[arg-type]

        self.assertIn('"fields"', content)
        self.assertEqual(client.call_count, 2)
        mock_sleep.assert_awaited_once()

    async def test_generate_does_not_retry_on_4xx(self) -> None:
        client = FlakyClient([MockResponse({}, status_code=400)])
        with patch.object(llm_client.settings, "OPENAI_API_KEY", "test-key"), patch(
            "backend.clients.llm_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with self.assertRaises(llm_client.LLMClientError):
                _ = await llm_client.generate("prompt", client=client)  # type: ignore[arg-type]

        self.assertEqual(client.call_count, 1)
        mock_sleep.assert_not_awaited()

    async def test_generate_raises_after_exhausting_retries_on_5xx(self) -> None:
        client = FlakyClient([MockResponse({}, status_code=503), MockResponse({}, status_code=503)])
        with patch.object(llm_client.settings, "OPENAI_API_KEY", "test-key"), patch(
            "backend.clients.llm_client.asyncio.sleep", new_callable=AsyncMock
        ):
            with self.assertRaises(llm_client.LLMClientError):
                _ = await llm_client.generate("prompt", client=client)  # type: ignore[arg-type]

        self.assertEqual(client.call_count, llm_client.MAX_ATTEMPTS)


if __name__ == "__main__":
    _ = unittest.main()
