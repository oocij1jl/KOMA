import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    _ = unittest.main()
