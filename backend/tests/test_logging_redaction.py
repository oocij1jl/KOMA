"""httpx 요청 로그에서 cert_key/authKey 값이 마스킹되는지 확인하는 테스트."""

from __future__ import annotations

import logging
import unittest

from backend.main import _RedactSensitiveQueryParams


class LoggingRedactionTests(unittest.TestCase):
    def _make_record(self, args: tuple[object, ...]) -> logging.LogRecord:
        return logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='HTTP Request: %s %s "%s %d %s"',
            args=args,
            exc_info=None,
        )

    def test_redacts_nl_cert_key_in_url(self) -> None:
        record = self._make_record(
            (
                "GET",
                "https://www.nl.go.kr/seoji/SearchApi.do?cert_key=SUPERSECRET&isbn=9788936434120",
                "HTTP/1.1",
                200,
                "OK",
            )
        )

        _RedactSensitiveQueryParams().filter(record)
        message = record.getMessage()

        self.assertNotIn("SUPERSECRET", message)
        self.assertIn("cert_key=***", message)
        self.assertIn("isbn=9788936434120", message)

    def test_redacts_d4l_auth_key_in_url(self) -> None:
        record = self._make_record(
            (
                "GET",
                "http://data4library.kr/api/srchDtlList?authKey=ANOTHERSECRET&isbn13=9788936434120",
                "HTTP/1.1",
                200,
                "OK",
            )
        )

        _RedactSensitiveQueryParams().filter(record)
        message = record.getMessage()

        self.assertNotIn("ANOTHERSECRET", message)
        self.assertIn("authKey=***", message)

    def test_leaves_status_code_type_and_unrelated_url_untouched(self) -> None:
        record = self._make_record(
            (
                "POST",
                "https://api.openai.com/v1/chat/completions",
                "HTTP/1.1",
                200,
                "OK",
            )
        )

        _RedactSensitiveQueryParams().filter(record)

        self.assertEqual(record.args[3], 200)
        self.assertIsInstance(record.args[3], int)
        self.assertEqual(record.args[1], "https://api.openai.com/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
