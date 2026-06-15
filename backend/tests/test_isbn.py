import unittest

from backend.utils.isbn import normalize_isbn


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


if __name__ == "__main__":
    unittest.main()
