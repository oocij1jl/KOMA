import re


ISBN10_RE = re.compile(r"^\d{9}[\dX]$")
ISBN13_RE = re.compile(r"^\d{13}$")


def normalize_isbn(raw: str) -> str:
    """하이픈 제거 후 형식 검증. 잘못된 ISBN은 ValueError."""
    isbn = raw.replace("-", "").strip()
    if not (ISBN10_RE.match(isbn) or ISBN13_RE.match(isbn)):
        raise ValueError(f"유효하지 않은 ISBN 형식: {raw!r}")
    return isbn
