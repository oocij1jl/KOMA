import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.clients import data4library_client


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


if __name__ == "__main__":
    unittest.main()
