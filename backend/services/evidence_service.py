import importlib
from typing import Any

try:  # pragma: no cover - import path depends on startup context
    from backend.utils.translation import detect_translation
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    detect_translation = importlib.import_module("utils.translation").detect_translation


def merge_evidence(
    biblio: dict[str, Any],
    keywords_result: dict[str, Any],
    usage_result: dict[str, Any],
    author_statements: list[str] | None = None,
) -> dict[str, Any]:
    """키워드 + 이용분석 + biblio 일부 → evidence (스키마 v2.1).

    번역 여부는 **모든 출처의 책임표시**에서 본다. 245에 쓸 문장은 하나만 고르지만,
    고르지 못한 쪽에만 '옮김'이 있는 책이 있어 한쪽만 보면 번역서를 놓친다.
    """
    keywords = keywords_result.get("keywords", [])
    co_loan_books = usage_result.get("co_loan_books", [])
    description = biblio.get("description", "")
    author = biblio.get("author", "")

    statements = [value for value in (author_statements or [author]) if value]
    translation_signals = detect_translation(" ; ".join(statements), description)
    available = _build_available_flags(
        keywords=keywords,
        description=description,
        co_loan_books=co_loan_books,
        translation_signals=translation_signals,
    )

    return {
        "keywords": keywords,
        "description": description,
        "co_loan_books": co_loan_books,
        "title": biblio.get("title", ""),
        "author": author,
        "kdc_from_api": biblio.get("kdc", ""),
        "ddc_from_api": biblio.get("ddc", ""),
        "translation_signals": translation_signals,
        "available": available,
    }


def _build_available_flags(
    *,
    keywords: list[Any],
    description: str,
    co_loan_books: list[Any],
    translation_signals: dict[str, Any],
) -> dict[str, bool]:
    return {
        "keywords": bool(keywords),
        "description": bool(description),
        "co_loan_books": bool(co_loan_books),
        "translation_signals": bool(translation_signals.get("detected")),
    }
