"""오프라인 재검증(ai/evaluation/revalidate_offline.py) 회귀 테스트.

재검증기는 backend 패키지 밖에 있으므로 경로로 직접 로드한다.
확인 대상은 세 가지다. (1) 생성 시점 스냅샷의 evidence를 그대로 써서 근거 있는
041/546이 재검증에서 살아남는지, (2) 근거가 없는 스냅샷을 "근거 없음"으로
취급해도 규칙 레이어 필드는 그대로 남는지, (3) 스냅샷이 없거나 다른 책이면
결과를 하나도 쓰지 않고 멈추는지.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[2]
REVALIDATOR_PATH = ROOT_DIR / "ai" / "evaluation" / "revalidate_offline.py"

ISBN = "9788936434120"
OTHER_ISBN = "9788936434595"
DESCRIPTION = "영어를 한국어로 번역한 책이다."


def _load_revalidator() -> Any:
    spec = importlib.util.spec_from_file_location("revalidate_offline_for_tests", REVALIDATOR_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - 경로 문제일 때만
        raise RuntimeError(f"재검증기를 로드할 수 없습니다: {REVALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


revalidate_offline = _load_revalidator()


def snapshot(
    *,
    isbn: str = ISBN,
    description_available: bool = True,
    translation_detected: bool = True,
    skipped_by_default: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "isbn": isbn,
        "biblio": {
            "found": True,
            "isbn_ea": isbn,
            "title": "채식주의자",
            "author": "한강 지음",
            "publisher": "창비",
        },
        "evidence": {
            "description": DESCRIPTION,
            "translation_signals": {"detected": translation_detected, "hints": ["옮김"]},
            "available": {
                "keywords": False,
                "description": description_available,
                "co_loan_books": False,
                "translation_signals": translation_detected,
            },
        },
    }
    if skipped_by_default is not None:
        payload["generate_options"] = {"skipped_by_default": skipped_by_default}
    return payload


def rule_field(tag: str, subfields: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "tag": tag,
        "source": "api",
        "generated_by": "rule",
        "indicator1": " ",
        "indicator2": " ",
        "subfields": subfields,
        "review_required": False,
        "confidence": "high",
        "evidence": None,
        "note": "biblio 전사",
    }


def llm_field(tag: str, subfields: list[dict[str, str]], indicator1: str = " ") -> dict[str, Any]:
    return {
        "tag": tag,
        "source": "ai_inference",
        "generated_by": "llm",
        "indicator1": indicator1,
        "indicator2": " ",
        "subfields": subfields,
        "review_required": True,
        "confidence": "medium",
        "evidence": {"from": ["description"], "keywords_used": [], "reasoning": "책소개의 번역 진술"},
        "note": "",
    }


def stored_result() -> dict[str, Any]:
    return {
        "fields": [
            rule_field("020", [{"code": "a", "value": ISBN}]),
            rule_field("245", [{"code": "a", "value": "채식주의자"}]),
            llm_field("041", [{"code": "a", "value": "kor"}], indicator1="1"),
            llm_field("546", [{"code": "a", "value": "영어를 한국어로 번역"}]),
            llm_field("500", [{"code": "a", "value": "원표제: The Vegetarian"}]),
        ],
        "skipped_fields": [],
        "warnings": [],
    }


def tags(payload: dict[str, Any]) -> list[str]:
    return [field["tag"] for field in payload["fields"]]


class RevalidateWithSnapshotTests(unittest.TestCase):
    def _revalidate(self, result: dict[str, Any], snapshot_payload: dict[str, Any]) -> dict[str, Any]:
        llm_input = revalidate_offline.LLMInputPayload.model_validate(snapshot_payload)
        new_payload, _removed, _changed = revalidate_offline.revalidate(result, llm_input=llm_input)
        return new_payload

    def test_snapshot_evidence_keeps_supported_language_fields(self) -> None:
        new_payload = self._revalidate(stored_result(), snapshot())

        self.assertIn("041", tags(new_payload))
        self.assertIn("546", tags(new_payload))

    def test_missing_evidence_snapshot_drops_language_fields_but_keeps_rule_fields(self) -> None:
        new_payload = self._revalidate(
            stored_result(), snapshot(description_available=False, translation_detected=False)
        )

        self.assertNotIn("041", tags(new_payload))
        self.assertNotIn("546", tags(new_payload))
        self.assertEqual(
            [field for field in new_payload["fields"] if field["generated_by"] == "rule"],
            [field for field in stored_result()["fields"] if field["generated_by"] == "rule"],
        )

    def test_snapshot_generation_scope_excludes_field_from_replay(self) -> None:
        kept = self._revalidate(stored_result(), snapshot())
        excluded = self._revalidate(stored_result(), snapshot(skipped_by_default=["500", "650", "830", "950"]))

        self.assertIn("500", tags(kept))
        self.assertNotIn("500", tags(excluded))

    def test_indicator_correction_is_reported_as_change_not_removal(self) -> None:
        payload = stored_result()
        language = next(field for field in payload["fields"] if field["tag"] == "041")
        language["indicator1"] = "0"
        llm_input = revalidate_offline.LLMInputPayload.model_validate(snapshot())

        result, removed, changed = revalidate_offline.revalidate(payload, llm_input=llm_input)

        self.assertEqual(next(field for field in result["fields"] if field["tag"] == "041")["indicator1"], "1")
        self.assertEqual(removed, [])
        self.assertEqual(changed, ["041"])


class SnapshotPairingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.in_dir = base / "results"
        self.inputs_dir = base / "inputs"
        self.out_dir = base / "revalidated"
        self.in_dir.mkdir()
        self.inputs_dir.mkdir()
        self._write(self.in_dir / f"{ISBN}.json", stored_result())

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _run_cli(self) -> int:
        argv = [
            "revalidate_offline.py",
            "--in-dir",
            str(self.in_dir),
            "--inputs-dir",
            str(self.inputs_dir),
            "--out-dir",
            str(self.out_dir),
        ]
        with patch.object(sys, "argv", argv), self.assertRaises(SystemExit) as caught:
            revalidate_offline.main()
        return int(caught.exception.code or 0)

    def test_snapshot_isbn_must_match_result_file_name(self) -> None:
        self._write(self.inputs_dir / f"{ISBN}.json", snapshot(isbn=OTHER_ISBN))

        with self.assertRaises(revalidate_offline.SnapshotError) as caught:
            revalidate_offline.load_llm_input(self.inputs_dir, ISBN)

        self.assertIn(OTHER_ISBN, str(caught.exception))

    def test_result_transcribing_another_isbn_is_rejected_against_snapshot(self) -> None:
        # 파일 이름은 맞지만 내용이 다른 책인 결과(이름 변경·디렉터리 섞임)를 거른다.
        misplaced = stored_result()
        misplaced["fields"][0]["subfields"] = [{"code": "a", "value": OTHER_ISBN}]
        llm_input = revalidate_offline.LLMInputPayload.model_validate(snapshot())

        with self.assertRaises(revalidate_offline.SnapshotError) as caught:
            revalidate_offline.revalidate(misplaced, llm_input=llm_input)

        self.assertIn(OTHER_ISBN, str(caught.exception))

    def test_missing_snapshot_stops_before_writing_any_result(self) -> None:
        code = self._run_cli()

        self.assertEqual(code, 2)
        self.assertFalse(self.out_dir.exists())

    def test_invalid_snapshot_stops_before_writing_any_result(self) -> None:
        (self.inputs_dir / f"{ISBN}.json").write_text('{"isbn": "x"}', encoding="utf-8")

        code = self._run_cli()

        self.assertEqual(code, 2)
        self.assertFalse(self.out_dir.exists())

    def test_output_cannot_overwrite_original_input_snapshot(self) -> None:
        original = snapshot()
        self._write(self.inputs_dir / f"{ISBN}.json", original)
        self.out_dir = self.inputs_dir

        self.assertEqual(self._run_cli(), 2)
        self.assertEqual(json.loads((self.inputs_dir / f"{ISBN}.json").read_text()), original)

    def test_matching_snapshot_writes_revalidated_result(self) -> None:
        self._write(self.inputs_dir / f"{ISBN}.json", snapshot())

        with patch.object(
            sys,
            "argv",
            [
                "revalidate_offline.py",
                "--in-dir",
                str(self.in_dir),
                "--inputs-dir",
                str(self.inputs_dir),
                "--out-dir",
                str(self.out_dir),
            ],
        ):
            revalidate_offline.main()

        written = json.loads((self.out_dir / f"{ISBN}.json").read_text(encoding="utf-8"))
        self.assertEqual(tags(written), ["020", "245", "041", "546", "500"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
