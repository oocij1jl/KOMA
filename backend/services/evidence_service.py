from typing import Any

try:  # pragma: no cover - import path depends on startup context
    from backend.utils.translation import detect_translation
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from utils.translation import detect_translation


def merge_evidence(
    biblio: dict[str, Any],
    keywords_result: dict[str, Any],
    usage_result: dict[str, Any],
) -> dict[str, Any]:
    """키워드 + 이용분석 + biblio 일부 → evidence (스키마 v2.1)."""
    keywords = keywords_result.get("keywords", [])
    co_loan_books = usage_result.get("co_loan_books", [])
    description = biblio.get("description", "")
    author = biblio.get("author", "")

    translation_signals = detect_translation(author, description)

    return {
        "keywords": keywords,
        "description": description,
        "co_loan_books": co_loan_books,
        "title": biblio.get("title", ""),
        "author": author,
        "kdc_from_api": biblio.get("kdc", ""),
        "ddc_from_api": biblio.get("ddc", ""),
        "translation_signals": translation_signals,
        "available": {
            "keywords": bool(keywords),
            "description": bool(description),
            "co_loan_books": bool(co_loan_books),
        },
    }
