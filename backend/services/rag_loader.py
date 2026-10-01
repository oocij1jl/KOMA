from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import cast


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAG_CHUNKS_DIR = PROJECT_ROOT / "ai" / "rag" / "chunks"
TAG_PATTERN = re.compile(r"^\d{3}$")


def _format_chunk(chunk: dict[str, object]) -> str:
    title = str(chunk.get("title") or chunk.get("chunk_id") or "untitled")
    section = str(chunk.get("section") or "")
    content = str(chunk.get("content") or "")

    header = f"- {title}"
    if section:
        header += f" ({section})"
    return f"{header}\n  {content}" if content else header


def load_rules(tags: list[str]) -> dict[str, str]:
    """태그별 RAG JSONL 규칙을 통째로 읽어 프롬프트용 텍스트로 반환한다.

    규칙 파일 없는 tag는 RAG 규칙 없이 간다. 예: 020/245 같은 단순 필드는
    `ai/rag/chunks/kormarc-<tag>.jsonl`이 없을 수 있으므로 예외를 내지 않는다.
    JSONL 파싱에 실패한 줄도 전체 로딩을 중단하지 않고 해당 줄만 건너뛴다.
    """

    rules: dict[str, str] = {}
    chunks_root = RAG_CHUNKS_DIR.resolve()

    for tag in tags:
        normalized_tag = str(tag).strip()
        if not normalized_tag:
            continue
        if TAG_PATTERN.fullmatch(normalized_tag) is None:
            logger.warning("Skipping invalid RAG rule tag: %s", normalized_tag)
            continue

        rule_path = (RAG_CHUNKS_DIR / f"kormarc-{normalized_tag}.jsonl").resolve()
        if rule_path.parent != chunks_root:
            logger.warning("Skipping RAG rule path outside chunks directory: tag=%s", normalized_tag)
            continue
        if not rule_path.exists():
            logger.debug("RAG rule file not found for tag %s", normalized_tag)
            continue

        chunks: list[str] = []
        with rule_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    loaded = cast(object, json.loads(stripped))
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Skipping malformed RAG JSONL line: tag=%s path=%s line=%s error=%s",
                        normalized_tag,
                        rule_path,
                        line_number,
                        exc,
                    )
                    continue

                if isinstance(loaded, dict):
                    chunk = cast(dict[str, object], loaded)
                    chunks.append(_format_chunk(chunk))
                else:
                    logger.warning(
                        "Skipping non-object RAG JSONL line: tag=%s path=%s line=%s",
                        normalized_tag,
                        rule_path,
                        line_number,
                    )

        if chunks:
            rules[normalized_tag] = "\n\n".join(chunks)

    return rules
