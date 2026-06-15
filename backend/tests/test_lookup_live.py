import os
import unittest

from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


LIVE_TEST_ISBN = os.getenv("LOOKUP_TEST_ISBN", "").strip()


@unittest.skipUnless(
    settings.NL_API_KEY and settings.D4L_API_KEY and LIVE_TEST_ISBN,
    "NL_API_KEY, D4L_API_KEY, LOOKUP_TEST_ISBN 이 모두 필요합니다.",
)
class LookupLiveTests(unittest.TestCase):
    def test_lookup_endpoint_returns_biblio_with_real_api_keys(self) -> None:
        client = TestClient(app)
        response = client.get("/api/lookup/isbn", params={"isbn": LIVE_TEST_ISBN})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["isbn"], LIVE_TEST_ISBN.replace("-", ""))
        self.assertIn("biblio", payload)
        self.assertIn("evidence", payload)
        self.assertIn("raw", payload)
        self.assertNotIn("found", payload)
        self.assertIn("translation_signals", payload["evidence"])
        self.assertIn("available", payload["evidence"])


if __name__ == "__main__":
    unittest.main()
