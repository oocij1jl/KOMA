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
    build_653_classification_field,
    build_deterministic_fields,
    classification_subject_terms,
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

    def test_compound_pagination_and_explicit_units_are_not_truncated(self) -> None:
        for page in (
            "xii, 250 p.",
            "400, [98] p.",
            "xv, 54, 54 p.",
            "1책 (xvi, 97, 100 p.)",
            "230 p., 25장",
            "2 v.",
            "149 pages",
            "27 leaves",
            "3권",
            "100면",
            "2매",
            "[24] p.",
            "xii p.",
        ):
            with self.subTest(page=page):
                field, skipped = build_300(biblio(page=page))
                assert field is not None
                self.assertIsNone(skipped)
                self.assertEqual(subfield_pairs(field), [("a", page)])

    def test_simple_positive_page_inputs_are_normalized(self) -> None:
        for page, expected in (("1", "1 p."), ("320p", "320 p."), ("320 pp.", "320 p.")):
            with self.subTest(page=page):
                field, _ = build_300(biblio(page=page))
                assert field is not None
                self.assertEqual(subfield_pairs(field), [("a", expected)])

    def test_zero_and_ambiguous_extents_do_not_invent_page_counts(self) -> None:
        for page in ("0", "000", "0 p.", "0책", "xii, 0 p.", "-5", "12.5", "200 words", "총 200", "250/300"):
            with self.subTest(page=page):
                field, _ = build_300(biblio(page=page, book_size="22 cm"))
                assert field is not None
                self.assertEqual(subfield_pairs(field), [("c", "22 cm")])

    def test_decimal_dimensions_follow_scalar_unit_policy(self) -> None:
        for size, expected in (
            ("22.5 cm", "22.5 cm"),
            ("19.8 cm", "19.8 cm"),
            ("22.05 CM", "22.05 cm"),
            ("224.5 mm", "23 cm"),
            ("220 mm", "22 cm"),
            ("220.1 mm", "23 cm"),
        ):
            with self.subTest(size=size):
                field, _ = build_300(biblio(book_size=size))
                assert field is not None
                self.assertEqual(subfield_pairs(field), [("c", expected)])

    def test_dimension_pairs_keep_service_height_policy_without_losing_decimals(self) -> None:
        for size, expected in (
            ("30 x 20 cm", "30 cm"),
            ("20 × 30 cm", "30 cm"),
            ("22.5 x 19.8 cm", "22.5 cm"),
            ("152.5*224.5mm", "23 cm"),
            ("188*257mm", "26 cm"),
            ("200*220.1mm", "23 cm"),
        ):
            with self.subTest(size=size):
                field, _ = build_300(biblio(book_size=size))
                assert field is not None
                self.assertEqual(subfield_pairs(field), [("c", expected)])

    def test_ambiguous_or_nonpositive_dimensions_are_deferred(self) -> None:
        for size in (
            "0 x 20 cm",
            "20 × 0 cm",
            "0 cm",
            "0.0 mm",
            "-22 cm",
            "22",
            "8 in.",
            "22 cm (케이스 30 cm)",
            "22 cmm",
        ):
            with self.subTest(size=size):
                field, _ = build_300(biblio(page="200", book_size=size))
                assert field is not None
                self.assertEqual(subfield_pairs(field), [("a", "200 p.")])
                self.assertIn(size, field.note)

    def test_invalid_extent_and_dimension_skip_the_field(self) -> None:
        field, skipped = build_300(biblio(page="0", book_size="0 cm"))

        self.assertIsNone(field)
        assert skipped is not None
        self.assertEqual(skipped.tag, "300")

    def test_illustration_subfield_is_never_generated(self) -> None:
        """삽화(▼b)는 근거가 없으므로 만들지 않는다."""

        field, _ = build_300(biblio(page="190 p", book_size="26 cm"))

        assert field is not None
        self.assertNotIn("b", {code for code, _ in subfield_pairs(field)})

    def test_unitless_numbers_are_treated_as_mm(self) -> None:
        """단위 표기가 없는 '128*188' 형태는 국중도/정보나루 API가 실제로 주는
        정상 포맷이다(2026-09-25 실API 응답 `book_size='188*257'` 확인). 관례상
        mm(가로*세로)로 보고 큰 값을 cm로 올림하며, 소수부도 버리지 않는다."""
        for size, expected in (("128*188", "19 cm"), ("200*220.1", "23 cm")):
            with self.subTest(size=size):
                field, _ = build_300(biblio(page="200", book_size=size))

                assert field is not None
                self.assertEqual(subfield_pairs(field), [("a", "200 p."), ("c", expected)])

    def test_small_unitless_number_is_not_guessed(self) -> None:
        """100 미만의 단위 없는 값은 이미 cm일 가능성이 있어 mm로 추정하지 않는다."""
        field, _ = build_300(biblio(page="200", book_size="22"))

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "200 p.")])

    def test_unrecognized_unit_text_is_not_guessed(self) -> None:
        field, _ = build_300(biblio(page="200", book_size="128*188in"))

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


class Subtitle245Tests(unittest.TestCase):
    def test_collected_subtitle_fills_subfield_b_when_title_has_no_separator(self) -> None:
        field, _ = build_245(
            biblio(title="카프카의 문장들", subtitle="희박한 희망을 채굴하다", author="프란츠 카프카 지음")
        )

        assert field is not None
        self.assertEqual(
            subfield_pairs(field),
            [("a", "카프카의 문장들"), ("b", "희박한 희망을 채굴하다"), ("d", "프란츠 카프카 지음")],
        )
        self.assertIn("국중도 상세 페이지", field.note)

    def test_title_separator_wins_over_collected_subtitle(self) -> None:
        field, _ = build_245(biblio(title="카프카의 문장들: 표제 안 부제", subtitle="수집한 부제"))

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "카프카의 문장들"), ("b", "표제 안 부제")])
        self.assertIn("표제 구분자", field.note)

    def test_subtitle_equal_to_main_title_is_not_duplicated(self) -> None:
        field, _ = build_245(biblio(title="민강", subtitle="민강"))

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "민강")])


class ClassificationSubjectTermTests(unittest.TestCase):
    def test_literature_terms_follow_language_and_genre_digits(self) -> None:
        for kdc, add_code, expected in (
            ("813.7", "03810", ["한국문학", "한국소설"]),
            ("811.7", "04810", ["한국문학", "한국시"]),
            ("814.7", "03810", ["한국문학", "한국에세이"]),
            ("854", "03850", ["독일문학", "독일에세이"]),
            ("850.99", "03850", ["독일문학"]),
        ):
            with self.subTest(kdc=kdc):
                self.assertEqual(
                    classification_subject_terms(biblio(kdc=kdc, isbn_add_code=add_code)), expected
                )

    def test_audience_digit_switches_children_and_youth_terms(self) -> None:
        self.assertEqual(
            classification_subject_terms(biblio(kdc="813.7", isbn_add_code="73810")),
            ["한국문학", "아동문학", "한국동화"],
        )
        self.assertEqual(
            classification_subject_terms(biblio(kdc="811.8", isbn_add_code="73810")),
            ["한국문학", "아동문학", "동시"],
        )
        self.assertEqual(
            classification_subject_terms(biblio(kdc="813.7", isbn_add_code="77810")),
            ["한국문학", "아동문학", "한국동화", "그림책"],
        )
        self.assertEqual(
            classification_subject_terms(biblio(kdc="813.7", isbn_add_code="44810")),
            ["한국문학", "청소년문학", "청소년소설"],
        )

    def test_non_literature_and_missing_classification_produce_nothing(self) -> None:
        for kdc, add_code in (("005.58", "13000"), ("911.05", "03910"), ("", "03810"), ("81", "03810")):
            with self.subTest(kdc=kdc):
                self.assertEqual(classification_subject_terms(biblio(kdc=kdc, isbn_add_code=add_code)), [])

    def test_rule_field_skips_terms_the_llm_already_wrote(self) -> None:
        field = build_653_classification_field(
            biblio(kdc="813.7", isbn_add_code="03810"), existing_terms=["한국 소설"]
        )

        assert field is not None
        self.assertEqual(subfield_pairs(field), [("a", "한국문학")])
        self.assertEqual((field.source, field.generated_by), ("api", "rule"))
        self.assertIsNone(field.evidence)
        self.assertTrue(field.review_required)
        self.assertIn("813.7", field.note)

    def test_rule_field_is_absent_when_every_term_exists(self) -> None:
        self.assertIsNone(
            build_653_classification_field(
                biblio(kdc="813.7", isbn_add_code="03810"), existing_terms=["한국문학", "한국소설"]
            )
        )


if __name__ == "__main__":
    unittest.main()
