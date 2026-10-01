from typing import Any


_TRANS_HINTS = ("옮김", "번역", "역자", "역주", "translated", "옮긴이")


def detect_translation(author: str, description: str) -> dict[str, Any]:
    """번역 정황 1차 탐지. detected와 근거 hints만 제공한다."""
    hints: list[str] = []
    blob = f"{author} {description}"
    for hint in _TRANS_HINTS:
        if hint in blob:
            hints.append(f"'{hint}' 표현 발견")
    return {"detected": bool(hints), "hints": hints}
