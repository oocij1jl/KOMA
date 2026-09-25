"""RAG 규칙 기반 평가 v2 회귀 테스트.

평가기(ai/evaluation/evaluate_v2.py)는 backend 패키지 밖에 있으므로 경로로
직접 로드한다. v1이 놓치던 오류(역할어가 인명으로 남음, 출판사 710, 245와
같은 246, 근거 없는 과잉 생성)가 v2 지표에 드러나는지 확인한다.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
EVALUATOR_PATH = ROOT_DIR / "ai" / "evaluation" / "evaluate_v2.py"


def _load_evaluator() -> Any:
    spec = importlib.util.spec_from_file_location("evaluate_v2_for_tests", EVALUATOR_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - 경로 문제일 때만
        raise RuntimeError(f"평가기를 로드할 수 없습니다: {EVALUATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evaluator = _load_evaluator()
v1 = evaluator.v1


def field(tag: str, subfields: list[tuple[str, str]], ind1: str = " ", ind2: str = " ", **extra: Any) -> dict[str, Any]:
    return {
        "tag": tag,
        "indicator1": ind1,
        "indicator2": ind2,
        "subfields": [{"code": code, "value": value} for code, value in subfields],
        **extra,
    }


def gold_record(tags: dict[str, list[tuple[str, str, list[tuple[str, str]]]]]) -> Any:
    return v1.RecordData(
        isbn="9788960909830",
        tags={
            tag: [v1.FieldOccurrence(indicator1=ind1, indicator2=ind2, subfields=subfields) for ind1, ind2, subfields in items]
            for tag, items in tags.items()
        },
    )


class NameTokenTests(unittest.TestCase):
    def test_role_words_are_removed_as_tokens(self) -> None:
        self.assertEqual(evaluator.name_tokens("엮고 옮긴이: 권혁준"), ["권혁준"])
        self.assertEqual(evaluator.name_tokens("저자: 이석진"), ["이석진"])
        self.assertEqual(evaluator.name_tokens("오가연 [공]지음"), ["오가연"])

    def test_role_word_inside_name_is_kept(self) -> None:
        self.assertEqual(evaluator.name_tokens("김저희 지음"), ["김저희"])


class Score700Tests(unittest.TestCase):
    def test_inverted_gold_name_matches_and_romanized_name_is_excluded(self) -> None:
        gold = gold_record(
            {
                "700": [
                    ("1", " ", [("a", "카프카, 프란츠,"), ("d", "1883-1924")]),
                    ("1", " ", [("a", "권혁준")]),
                    ("1", " ", [("a", "Kafka, Frantz")]),
                ]
            }
        )
        payload = {"fields": [field("700", [("a", "프란츠 카프카")]), field("700", [("a", "권혁준"), ("e", "옮김")])]}

        result = evaluator.score_700(gold, payload)

        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["gold_only"], [])

    def test_missing_700_scores_zero(self) -> None:
        gold = gold_record({"700": [("1", " ", [("a", "정보라")])]})

        self.assertEqual(evaluator.score_700(gold, {"fields": []})["score"], 0.0)


class RuleTests(unittest.TestCase):
    def test_245_responsibility_in_c_is_a_violation(self) -> None:
        payload = {"fields": [field("245", [("a", "처단"), ("c", "정보라 지음")], ind1="1", ind2="0")]}

        failures = evaluator.rule_results(payload)["R-245"]

        self.assertIn("245$c 사용(책임표시는 $d/$e)", failures)
        self.assertIn("245 제1지시기호 '1'", failures)
        # 같은 245$c를 식별기호 규칙에서 한 번 더 감점하지 않는다.
        self.assertEqual(evaluator.rule_results(payload)["S-codes"], [])

    def test_publisher_as_710_is_a_violation(self) -> None:
        payload = {
            "fields": [
                field("260", [("b", "마음산책"), ("c", "2026")]),
                field("710", [("a", "마음산책")], ind1="2"),
            ]
        }

        self.assertEqual(evaluator.rule_results(payload)["R-710"], ["710 출판사를 단체저자로 '마음산책'"])

    def test_246_equal_to_title_is_a_violation(self) -> None:
        payload = {
            "fields": [
                field("245", [("a", "끝까지 해 보자, 때밀이 장갑!")], ind1="0", ind2="0"),
                field("246", [("a", "끝까지 해 보자 때밀이 장갑")], ind1="3"),
            ]
        }

        self.assertEqual(len(evaluator.rule_results(payload)["R-246"]), 1)

    def test_rule_is_not_applicable_without_field(self) -> None:
        self.assertIsNone(evaluator.rule_results({"fields": []})["R-710"])

    def test_translation_546_is_not_generic(self) -> None:
        payload = {"fields": [field("546", [("a", "한국어 번역본")])]}

        self.assertEqual(evaluator.rule_results(payload)["R-546"], [])

    def test_negated_546_is_a_violation(self) -> None:
        payload = {"fields": [field("546", [("a", "자료의 언어 정보는 원문에서 확인되지 않음")])]}

        self.assertEqual(len(evaluator.rule_results(payload)["R-546"]), 1)


class DecisionTests(unittest.TestCase):
    def test_correct_abstention_counts_as_true_negative(self) -> None:
        gold = gold_record({"440": [("0", "0", [("a", "문장들;"), ("v", "10")])]})
        payload = {"fields": [field("546", [("a", "한국어로 된 자료")])]}

        outcomes = evaluator.decision_outcomes(gold, payload)

        self.assertEqual(outcomes["250"], "TN")
        self.assertEqual(outcomes["546"], "FP")
        # 기관 레코드의 440은 490에 대응한다.
        self.assertEqual(outcomes["490"], "FN")


if __name__ == "__main__":
    _ = unittest.main()
