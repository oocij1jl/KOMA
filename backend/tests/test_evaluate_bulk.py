"""대량 평가의 재개 및 도서 단위 집계 회귀 테스트."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


EVALUATOR_PATH = Path(__file__).resolve().parents[2] / "ai/evaluation/evaluate_bulk.py"
spec = importlib.util.spec_from_file_location("evaluate_bulk_for_tests", EVALUATOR_PATH)
assert spec is not None and spec.loader is not None
evaluator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = evaluator
spec.loader.exec_module(evaluator)


class BulkEvaluationTests(unittest.TestCase):
    def test_resume_retries_failure_and_missing_output_without_replacing_success(self) -> None:
        rows = [evaluator.IsbnRow(str(i), str(i), "test", False) for i in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = json.dumps({"isbn": "0", "status": "success", "result": {"fields": []}})
            (root / "0.json").write_text(completed)
            (root / "1.json").write_text(json.dumps({"isbn": "1", "status": "error"}))
            recovered = [
                {"isbn": isbn, "status": "success", "result": {"fields": []}}
                for isbn in ("1", "2")
            ]
            with patch.object(evaluator, "call_generate_bulk", return_value=recovered) as generate, patch.object(
                evaluator, "call_validate", return_value={"valid": True}
            ):
                evaluator.collect_results(
                    rows, base_url="unused", results_dir=root, sleep_seconds=0, force_regenerate=False
                )
            generate.assert_called_once_with("unused", ["1", "2"])
            self.assertEqual((root / "0.json").read_text(), completed)
            metrics = evaluator.compute_metrics(rows, evaluator.load_cached_results(root))
            self.assertEqual(metrics["status_counts"], {"success": 3})
            self.assertEqual(metrics["success_rate"], 1.0)

    def test_unprocessed_books_are_not_counted_as_processed(self) -> None:
        rows = [evaluator.IsbnRow(str(i), str(i), "test", False) for i in range(3)]
        metrics = evaluator.compute_metrics(rows, {"0": {"status": "success"}, "1": {"status": "error"}})
        self.assertEqual(metrics["processed"], 2)
        self.assertEqual(metrics["status_counts"]["not_processed"], 1)
        self.assertEqual(metrics["success_rate"], 0.3333)

    def test_repeated_fields_count_as_one_book_for_presence_rate(self) -> None:
        rows = [evaluator.IsbnRow(str(i), str(i), "test", False) for i in range(2)]
        cached = {
            "0": {"status": "success", "result": {"fields": [{"tag": "700"}, {"tag": "700"}]}},
            "1": {"status": "success", "result": {"fields": []}},
        }
        self.assertEqual(evaluator.compute_metrics(rows, cached)["field_presence_rate"]["700"], 0.5)
