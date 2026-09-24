"""245 평가 규칙 회귀 테스트.

평가기(ai/evaluation/evaluate_koma.py)는 backend 패키지 밖에 있으므로
경로로 직접 로드한다. 이 테스트는 사서가 그대로 쓸 수 없는 245 오류
(책임표시를 ▼c에 넣기, 저자명을 ▼h에 넣기, 본표제 누락, 반복 생성)가
지표에 드러나는지 확인한다.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
EVALUATOR_PATH = ROOT_DIR / "ai" / "evaluation" / "evaluate_koma.py"


def _load_evaluator() -> Any:
    spec = importlib.util.spec_from_file_location("evaluate_koma_for_tests", EVALUATOR_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - 경로 문제일 때만
        raise RuntimeError(f"평가기를 로드할 수 없습니다: {EVALUATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evaluator = _load_evaluator()


def gold_245(subfields: list[tuple[str, str]]) -> evaluator.RecordData:
    return evaluator.RecordData(
        isbn="9791194630678",
        tags={"245": [evaluator.FieldOccurrence(indicator1="0", indicator2="0", subfields=subfields)]},
    )


def koma_payload(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {"fields": fields, "skipped_fields": [], "warnings": []}


def field_245(subfields: list[dict[str, str]], *, indicator1: str = "0", indicator2: str = "0") -> dict[str, Any]:
    return {
        "tag": "245",
        "indicator1": indicator1,
        "indicator2": indicator2,
        "subfields": subfields,
        "source": "api",
    }


class Evaluate245Tests(unittest.TestCase):
    def _compare(self, gold: evaluator.RecordData, payload: dict[str, Any]) -> dict[str, Any]:
        result = evaluator.compare_record(gold, payload, allow_partial_653=True)
        return result["field_results"]["245"]

    def test_responsibility_in_subfield_c_is_a_violation(self) -> None:
        """KORMARC 245에 ▼c는 없다. 값이 맞아도 정확으로 세면 안 된다."""

        gold = gold_245([("a", "모두의 노션 AI:"), ("b", "초보자도 바로 써먹는 노션 입문서/"), ("d", "임대균,"), ("e", "오가연 [공]지음")])
        payload = koma_payload(
            [
                field_245(
                    [
                        {"code": "a", "value": "모두의 노션 AI"},
                        {"code": "b", "value": "초보자도 바로 써먹는 노션 입문서"},
                        {"code": "c", "value": "임대균 오가연 지음"},
                    ]
                )
            ]
        )

        field_result = self._compare(gold, payload)

        self.assertIn("245$c 정의되지 않은 식별기호", field_result["violations"])
        self.assertFalse(field_result["accurate"])

    def test_author_in_subfield_h_is_a_violation(self) -> None:
        """▼h는 자료유형표시다. 저자명을 넣으면 오류다."""

        gold = gold_245([("a", "단종 애사/"), ("d", "장선경 글")])
        payload = koma_payload(
            [field_245([{"code": "a", "value": "단종 애사"}, {"code": "h", "value": "장선경"}])]
        )

        field_result = self._compare(gold, payload)

        self.assertIn("245$h 자료유형표시에 다른 값이 들어감", field_result["violations"])
        self.assertFalse(field_result["accurate"])

    def test_correct_subfields_are_accurate(self) -> None:
        """▼d/▼e로 올바르게 나누면 역할어 표기가 달라도 정확으로 센다."""

        gold = gold_245([("a", "사북 할아버지의 수상한 여행/"), ("d", "이규희 글;"), ("e", "방새미 그림")])
        payload = koma_payload(
            [
                field_245(
                    [
                        {"code": "a", "value": "사북 할아버지의 수상한 여행"},
                        {"code": "d", "value": "이규희 글"},
                        {"code": "e", "value": "방새미 그림"},
                    ]
                )
            ]
        )

        field_result = self._compare(gold, payload)

        self.assertEqual(field_result["violations"], [])
        self.assertEqual(field_result["status"], "exact")
        self.assertTrue(field_result["accurate"])

    def test_missing_responsibility_lowers_score(self) -> None:
        """표제만 맞고 책임표시가 없으면 정확이 아니라 부분 일치다."""

        gold = gold_245([("a", "계단의 왕/"), ("d", "정진호 지음")])
        payload = koma_payload([field_245([{"code": "a", "value": "계단의 왕"}])])

        field_result = self._compare(gold, payload)

        self.assertEqual(field_result["status"], "partial")
        self.assertFalse(field_result["accurate"])
        self.assertEqual(field_result["detail"]["components"]["responsibility"], 0.0)

    def test_repeated_245_is_a_violation(self) -> None:
        """245는 반복불가 필드다."""

        gold = gold_245([("a", "계단의 왕/"), ("d", "정진호 지음")])
        payload = koma_payload(
            [
                field_245([{"code": "a", "value": "계단의 왕"}, {"code": "d", "value": "정진호 지음"}]),
                field_245([{"code": "a", "value": "계단의 왕"}]),
            ]
        )

        field_result = self._compare(gold, payload)

        self.assertIn("245 반복불가 필드가 2회 생성됨", field_result["violations"])
        self.assertFalse(field_result["accurate"])

    def test_missing_title_subfield_is_a_violation(self) -> None:
        """▼a 본표제가 없으면 245로 성립하지 않는다."""

        gold = gold_245([("a", "계단의 왕/"), ("d", "정진호 지음")])
        payload = koma_payload([field_245([{"code": "d", "value": "정진호 지음"}])])

        field_result = self._compare(gold, payload)

        self.assertIn("245$a 본표제 누락", field_result["violations"])
        self.assertFalse(field_result["accurate"])

    def test_extra_subtitle_is_reported(self) -> None:
        """gold에 없는 부제를 만들어 내면 detail에 드러난다."""

        gold = gold_245([("a", "밤의 공항/"), ("d", "이원석 지음")])
        payload = koma_payload(
            [
                field_245(
                    [
                        {"code": "a", "value": "밤의 공항"},
                        {"code": "b", "value": "공항에서 보낸 열두 밤"},
                        {"code": "d", "value": "이원석 지음"},
                    ]
                )
            ]
        )

        field_result = self._compare(gold, payload)

        self.assertTrue(field_result["detail"]["extra_subtitle"])

    def test_responsibility_names_ignore_roles_and_brackets(self) -> None:
        """역할어와 각괄호 표기는 이름 비교에서 제외한다."""

        occurrence = evaluator.FieldOccurrence(
            indicator1="0",
            indicator2="0",
            subfields=[("d", "서윤빈 [외]글,"), ("e", "모차 그림")],
        )

        self.assertEqual(evaluator.responsibility_names(occurrence), {"서윤빈", "모차"})


if __name__ == "__main__":
    unittest.main()
