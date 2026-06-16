import re


ISBN10_RE = re.compile(r"^\d{9}[\dX]$")
ISBN13_RE = re.compile(r"^\d{13}$")


def normalize_isbn(raw: str) -> str:
    """하이픈 제거 후 형식 검증. 잘못된 ISBN은 ValueError."""
    isbn = raw.replace("-", "").strip()
    if not (ISBN10_RE.match(isbn) or ISBN13_RE.match(isbn)):
        raise ValueError(f"유효하지 않은 ISBN 형식: {raw!r}")
    return isbn


def _calculate_isbn13_check_digit(first_twelve_digits: str) -> str:
    total = 0
    for index, digit_char in enumerate(first_twelve_digits):
        digit = int(digit_char)
        total += digit if index % 2 == 0 else digit * 3

    check_digit = (10 - (total % 10)) % 10
    return str(check_digit)


def to_isbn13(isbn: str) -> str:
    """ISBN을 13자리 숫자 문자열로 통일한다."""
    normalized = normalize_isbn(isbn)
    if ISBN13_RE.match(normalized):
        expected = _calculate_isbn13_check_digit(normalized[:12])
        if normalized[-1] != expected:
            raise ValueError(f"ISBN-13 체크섬 오류: {isbn!r} (기대값 {expected})")
        return normalized

    isbn10_body = normalized[:9]
    isbn13_body = f"978{isbn10_body}"
    return f"{isbn13_body}{_calculate_isbn13_check_digit(isbn13_body)}"
