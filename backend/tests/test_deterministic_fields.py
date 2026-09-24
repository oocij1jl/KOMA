"""규칙 레이어(245/300/056/082) 테스트.

이 필드들은 LLM이 아니라 biblio에서 코드가 만든다. 값을 지어내지 않는지,
KORMARC 식별기호에 맞게 배치하는지, 근거가 없으면 skip하는지 확인한다.
"""
import unittest

from backend.schemas.lookup import BiblioSchema
from backend.services.deterministic_fields import (
    build_056,
    build_082,
    build_245,
    build_300,
    build_deterministic_fields,
    split_responsibility,
)


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

    def test_build_deterministic_fields_covers_all_rule_tags(self) -> None:
        fields, skipped = build_deterministic_fields(
            biblio(
                isbn_ea="9791194630678",
                isbn_add_code="13000",
                title="처단",
                author="정보라 지음",
                publisher="래빗홀",
                publish_year="2026",
                page="320 p",
                book_size="128*188mm",
                kdc="813.7",
            )
        )

        self.assertEqual([field.tag for field in fields], ["020", "245", "260", "300", "056"])
        # 값이 없는 필드는 추론하지 않고 skip한다.
        self.assertEqual([item.tag for item in skipped], ["250", "490", "082"])


class Build300Tests(unittest.TestCase):
    def test_page_and_size_conversion(self) -> None:
        field, skipped = build_300(biblio(page="320 p", book_size="128*188mm"))

        assert field is not None
        self.assertIsNone(skipped)
        # 세로 188mm는 19cm로 올림한다.
        self.assertEqual(subfield_pairs(field), [("a", "320 p."), ("c", "19 cm")])
        self.assertEqual((field.indicator1, field.indicator2), (" ", " "))
        self.assertEqual(field.generated_by, "rule")

    def test_cm_size_is_kept(self) -> None:
        field, _ = build_300(biblio(page="176", book_size="20 cm"))

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "176 p."), ("c", "20 cm")])

    def test_korean_unit_is_preserved(self) -> None:
        field, _ = build_300(biblio(page="152장", book_size="26 cm"))

        assert field is not None
        self.assertEqual(subfield_pairs(field)[0], ("a", "152장"))

    def test_illustration_subfield_is_never_generated(self) -> None:
        """삽화(▼b)는 근거가 없으므로 만들지 않는다."""

        field, _ = build_300(biblio(page="190 p", book_size="26 cm"))

        assert field is not None
        self.assertNotIn("b", {code for code, _ in subfield_pairs(field)})

    def test_unknown_unit_drops_size_only(self) -> None:
        field, _ = build_300(biblio(page="200", book_size="128*188"))

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "200 p.")])

    def test_missing_extent_and_size_is_skipped(self) -> None:
        field, skipped = build_300(biblio())

        self.assertIsNone(field)
        assert skipped is not None
        self.assertIn("형태사항 근거 없음", skipped.reason)


class ClassificationTests(unittest.TestCase):
    def test_kdc_is_transcribed_without_edition(self) -> None:
        field, skipped = build_056(biblio(kdc="005.58"))

        assert field is not None
        self.assertIsNone(skipped)
        self.assertEqual(subfield_pairs(field), [("a", "005.58")])
        self.assertEqual((field.indicator1, field.indicator2), (" ", " "))
        self.assertTrue(field.review_required)
        self.assertIn("판차 미수집", field.note)

    def test_kdc_edition_is_used_when_available(self) -> None:
        field, _ = build_056(biblio(kdc="813.7", kdc_edition="6"))

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "813.7"), ("2", "6")])

    def test_missing_kdc_is_skipped_not_inferred(self) -> None:
        field, skipped = build_056(biblio(description="생물학 입문서"))

        self.assertIsNone(field)
        assert skipped is not None
        self.assertIn("KDC 근거 없음", skipped.reason)

    def test_missing_ddc_is_skipped(self) -> None:
        field, skipped = build_082(biblio(kdc="813.7"))

        self.assertIsNone(field)
        assert skipped is not None
        self.assertIn("DDC 근거 없음", skipped.reason)


if __name__ == "__main__":
    unittest.main()
