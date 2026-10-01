"""일시 장애와 일일 제한에 대한 평가 실행기 상태 전이."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

PATH = Path(__file__).resolve().parents[2] / "ai/evaluation/run_daily_bulk.py"
spec = importlib.util.spec_from_file_location("daily_bulk_for_tests", PATH)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class DailyBulkTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, failure: str, initial_used: int = 0) -> tuple[dict, dict, list[str]]:
        rows = [runner.bulk.IsbnRow(str(i), str(i), "test", False) for i in range(500)]
        original_client = httpx.AsyncClient
        urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            urls.append(request.url.path)
            if len(urls) == 1:
                if failure == "timeout":
                    raise httpx.ConnectTimeout("temporary", request=request)
                if failure == "quota":
                    return httpx.Response(429, json={"response": {"error": "daily quota exceeded"}})
            return httpx.Response(200, json={"response": {}})

        async def generate(client: httpx.AsyncClient, sem: asyncio.Semaphore, isbn: str, capture: dict | None = None) -> dict:
            await asyncio.gather(*[
                client.get("https://data4library.kr/api/" + endpoint)
                for endpoint in ("srchDtlList", "keywordList", "usageAnalysisList")
            ], return_exceptions=True)
            return {"isbn": isbn, "status": "error", "error_code": "not_found"}

        async def no_sleep(seconds: float) -> None:
            return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(isbn_csv=root / "input.csv", out_dir=root, daily_call_budget=450,
                                      initial_used_calls=initial_used, max_books=1, once=True)
            config = SimpleNamespace(OPENAI_API_KEY="fake", NL_API_KEY="fake", D4L_API_KEY="fake",
                                     D4L_SKIP_USAGE=False, OPENAI_MODEL="test-model")
            with patch.object(runner.bulk, "read_isbn_csv", return_value=rows), patch.object(
                runner, "settings", config
            ), patch.object(runner, "_generate_one", side_effect=generate), patch.object(
                runner.asyncio, "sleep", side_effect=no_sleep
            ), patch.object(runner.httpx, "AsyncClient", side_effect=lambda **kw: original_client(
                transport=httpx.MockTransport(handler), **kw
            )):
                await runner.run(args)
            state = json.loads((root / "state.json").read_text())
            cached = runner.bulk.load_cached_results(root / "results")
            return state, cached, urls

    async def test_timeout_retries_with_budget_without_pausing_entire_day(self) -> None:
        state, cached, urls = await self.exercise("timeout")
        self.assertEqual(len(urls), 6)
        self.assertEqual(state["d4l_requests"], 6)
        self.assertIsNone(state["paused_day"])
        self.assertEqual(cached["0"]["error_code"], "not_found")
        self.assertNotIn("deferred", cached["0"])

    async def test_quota_response_defers_isbn_without_immediate_retry(self) -> None:
        state, cached, urls = await self.exercise("quota")
        self.assertEqual(len(urls), 3)
        self.assertEqual(state["paused_day"], state["day"])
        self.assertTrue(cached["0"]["deferred"])
        self.assertEqual(cached["0"]["error_code"], "d4l_incomplete")

    async def test_no_book_starts_without_budget_for_all_three_d4l_requests(self) -> None:
        state, cached, urls = await self.exercise("none", initial_used=448)
        self.assertEqual(urls, [])
        self.assertEqual(cached, {})
        self.assertEqual(state["d4l_requests"], 448)


class EvidenceContractTests(unittest.TestCase):
    def test_alias_free_evidence_stops_the_run_instead_of_being_saved(self) -> None:
        fields = [{"tag": "700", "evidence": {"from_": ["author"], "reasoning": "저자"}}]

        with self.assertRaisesRegex(SystemExit, "근거 키가 'from'이 아니다"):
            runner._assert_published_evidence_key("9791198682550", fields)

    def test_published_evidence_and_evidence_free_fields_pass(self) -> None:
        fields = [
            {"tag": "700", "evidence": {"from": ["author"], "reasoning": "저자"}},
            {"tag": "020", "evidence": None},
        ]

        self.assertIsNone(runner._assert_published_evidence_key("9791198682550", fields))
