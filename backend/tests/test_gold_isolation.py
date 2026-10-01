"""정답(gold) MARC가 생성 입력으로 새어 들어가지 않는지 검사한다.

정답을 가져온 국중도 소장자료 목록(detailSearch/marcDownload)이 생성 단계의 입력으로
쓰이면 정확도는 자기복사가 된다. 생성 경로가 실제로 호출하는 주소와, 생성 실행기에
넘기는 데이터셋 컬럼 두 가지를 모두 검사한다.
"""
from __future__ import annotations

import asyncio
import csv
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from backend.routers.generate import _generate_one

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = REPO_ROOT / "ai/evaluation/gold/gold500-20261001"
RUN_DIR = REPO_ROOT / "ai/evaluation/runs/gold500-20261001"

# 정답 MARC를 내려받는 국중도 소장자료 목록 경로. 생성 단계에서는 하나도 호출하면 안 된다.
GOLD_ONLY_PATHS = ("/NL/contents/search.do", "/NL/marcDownload.do", "/NL/search/openApi/search.do")
ALLOWED_HOSTS = {
    "www.nl.go.kr",  # 서지정보(SearchApi.do)
    "nl.go.kr",  # ISBN/CIP 상세 페이지
    "data4library.kr",
    "search.kyobobook.co.kr",
    "product.kyobobook.co.kr",
    "www.aladin.co.kr",
    "api.openai.com",
}


class GoldIsolationTests(unittest.TestCase):
    def test_generation_never_calls_the_gold_marc_endpoints(self) -> None:
        requested: list[httpx.URL] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(request.url)
            return httpx.Response(200, json={})

        async def exercise() -> None:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await _generate_one(client, asyncio.Semaphore(1), "9791198682550")

        with patch("backend.routers.generate.generate_marc_result", new=AsyncMock()):
            asyncio.run(exercise())

        self.assertTrue(requested, "조회 단계가 아무 요청도 하지 않아 검사가 무의미하다")
        for url in requested:
            self.assertIn(url.host, ALLOWED_HOSTS, f"허용되지 않은 출처 호출: {url}")
            for path in GOLD_ONLY_PATHS:
                self.assertNotEqual(url.path, path, f"정답 경로를 생성 단계에서 호출했다: {url}")

    def test_generation_dataset_carries_no_bibliographic_values(self) -> None:
        with (GOLD_DIR / "dataset.csv").open(encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, ["id", "isbn", "category", "reference_available"])
            rows = list(reader)

        self.assertEqual(len(rows), 500)
        self.assertEqual(len({row["isbn"] for row in rows}), 500)

    def test_gold_marc_is_stored_outside_the_generation_run_directory(self) -> None:
        gold = (GOLD_DIR / "gold.mrc").resolve()
        self.assertTrue(gold.exists())
        self.assertNotIn(RUN_DIR.resolve(), gold.parents)
        self.assertEqual(list(RUN_DIR.glob("**/*.mrc")), [])


if __name__ == "__main__":
    _ = unittest.main()
