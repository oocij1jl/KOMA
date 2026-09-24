"""규칙 레이어(245) 테스트.

245는 LLM이 아니라 biblio에서 코드가 만든다. 값을 지어내지 않는지,
KORMARC 식별기호에 맞게 배치하는지 확인한다.
"""

import unittest

from backend.schemas.lookup import BiblioSchema
from backend.services.deterministic_fields import build_245, build_deterministic_fields, split_responsibility


def biblio(**overrides: object) -> BiblioSchema:
    data: dict[str, object] = {"found": True, "field_sources": {}}
    data.update(overrides)
    return BiblioSchema.model_validate(data)


def subfield_pairs(field: object) -> list[tuple[str, str]]:
    return [(subfield.code, subfield.value) for subfield in field.subfields]  # type: ignore[attr-defined]


class Build245Tests(unittest.TestCase):
    def test_title_and_single_responsibility(self) -> None:
        field, skipped = build_245(biblio(title="계단의 왕", author="정진호"))

        assert field is not None
        self.assertIsNone(skipped)
        self.assertEqual(subfield_pairs(field), [("a", "계단의 왕"), ("d", "정진호")])
        self.assertEqual((field.indicator1, field.indicator2), ("0", "0"))
        self.assertEqual(field.source, "api")
        self.assertEqual(field.generated_by, "rule")
        self.assertIsNone(field.evidence)

    def test_responsibility_never_uses_subfield_c_or_h(self) -> None:
        """중간발표 결과의 대표 오류. 책임표시는 ▼d/▼e여야 한다."""

        field, _ = build_245(biblio(title="모두의 노션 AI", author="임대균 오가연 지음"))

        assert field is not None
        codes = {code for code, _ in subfield_pairs(field)}
        self.assertNotIn("c", codes)
        self.assertNotIn("h", codes)
        self.assertIn("d", codes)

    def test_role_words_split_first_and_later_statements(self) -> None:
        field, _ = build_245(biblio(title="사북 할아버지의 수상한 여행", author="이규희 글 방새미 그림"))

        assert field is not None
        self.assertEqual(
            subfield_pairs(field),
            [("a", "사북 할아버지의 수상한 여행"), ("d", "이규희 글"), ("e", "방새미 그림")],
        )

    def test_semicolon_splits_statements(self) -> None:
        field, _ = build_245(biblio(title="우리 아파트에 염소가 이사 왔다", author="장희주 글 ;최혜진 그림"))

        assert field is not None
        self.assertEqual(
            subfield_pairs(field),
            [("a", "우리 아파트에 염소가 이사 왔다"), ("d", "장희주 글"), ("e", "최혜진 그림")],
        )

    def test_leading_role_word_is_not_a_split_point(self) -> None:
        """'지은이 박아림'은 역할어가 앞에 붙은 한 덩어리다."""

        field, _ = build_245(biblio(title="하루 종일 네 생각", author="지은이 박아림"))

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "하루 종일 네 생각"), ("d", "지은이 박아림")])

    def test_names_without_role_words_are_not_split(self) -> None:
        """역할어가 없으면 공백만 보고 인명을 쪼개지 않는다."""

        self.assertEqual(split_responsibility("임봉근 임다운"), ["임봉근 임다운"])

    def test_subtitle_split_only_with_separator(self) -> None:
        with_separator, _ = build_245(biblio(title="카프카의 문장들 : 희박한 희망을 채굴하다"))
        without_separator, _ = build_245(biblio(title="카프카의 문장들"))

        assert with_separator is not None
        assert without_separator is not None
        self.assertEqual(
            subfield_pairs(with_separator),
            [("a", "카프카의 문장들"), ("b", "희박한 희망을 채굴하다")],
        )
        self.assertEqual(subfield_pairs(without_separator), [("a", "카프카의 문장들")])

    def test_parallel_title_uses_subfield_x(self) -> None:
        field, _ = build_245(biblio(title="그림 형제 = Brother Grimm", author="하시모토 다카시 지음 육아리 옮김"))

        assert field is not None
        self.assertEqual(
            subfield_pairs(field),
            [
                ("a", "그림 형제"),
                ("x", "Brother Grimm"),
                ("d", "하시모토 다카시 지음"),
                ("e", "육아리 옮김"),
            ],
        )

    def test_volume_uses_subfield_n(self) -> None:
        field, _ = build_245(biblio(title="역사 속의 세계사", volume="1", author="홍길동 지음"))

        assert field is not None
        self.assertEqual(
            subfield_pairs(field),
            [("a", "역사 속의 세계사"), ("n", "1"), ("d", "홍길동 지음")],
        )

    def test_parenthetical_prefix_sets_indicator2(self) -> None:
        field, _ = build_245(biblio(title="(컴퓨터로 즐기는) 도스게임 26가지"))

        assert field is not None
        self.assertEqual(field.indicator2, "1")

    def test_missing_author_still_generates_title(self) -> None:
        field, _ = build_245(biblio(title="밤의 공항"))

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "밤의 공항")])
        self.assertTrue(field.review_required)

    def test_missing_title_is_skipped(self) -> None:
        field, skipped = build_245(biblio(title="", author="이원석 지음"))

        self.assertIsNone(field)
        assert skipped is not None
        self.assertEqual(skipped.tag, "245")
        self.assertIn("표제 근거 없음", skipped.reason)

    def test_build_deterministic_fields_returns_245(self) -> None:
        fields, skipped = build_deterministic_fields(biblio(title="처단", author="정보라 지음"))

        self.assertEqual([field.tag for field in fields], ["245"])
        self.assertEqual(skipped, [])


if __name__ == "__main__":
    unittest.main()
