import unittest

from backend.utils.isbn import normalize_isbn, to_isbn13


class NormalizeIsbnTests(unittest.TestCase):
    def test_normalizes_13_digit_isbn(self) -> None:
        self.assertEqual(normalize_isbn("979-11-941600-0-4"), "9791194160004")

    def test_normalizes_10_digit_isbn(self) -> None:
        self.assertEqual(normalize_isbn("89-364-3412-X"), "893643412X")

    def test_strips_whitespace(self) -> None:
        self.assertEqual(normalize_isbn(" 9791194160004 "), "9791194160004")

    def test_rejects_invalid_isbn(self) -> None:
        with self.assertRaisesRegex(ValueError, "유효하지 않은 ISBN 형식"):
            normalize_isbn("abc")

    def test_converts_isbn10_to_isbn13(self) -> None:
        self.assertEqual(to_isbn13("89-364-3412-X"), "9788936434120")

    def test_keeps_isbn13_unchanged(self) -> None:
        self.assertEqual(to_isbn13("978-0-306-40615-7"), "9780306406157")

    def test_calculates_isbn13_checksum_correctly(self) -> None:
        self.assertEqual(to_isbn13("0306406152"), "9780306406157")

    def test_to_isbn13_rejects_invalid_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "유효하지 않은 ISBN 형식"):
            to_isbn13("123")

    def test_to_isbn13_rejects_invalid_isbn13_checksum(self) -> None:
        with self.assertRaisesRegex(ValueError, "ISBN-13 체크섬 오류"):
            to_isbn13("9788936434121")


if __name__ == "__main__":
    unittest.main()
