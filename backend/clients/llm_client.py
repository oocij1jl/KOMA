from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

try:  # pragma: no cover - import path depends on startup context
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from config import settings


logger = logging.getLogger(__name__)

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 45.0
MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 1.0


class LLMClientError(RuntimeError):
    """LLM 호출 실패를 라우터/서비스 계층에서 구분하기 위한 예외."""


async def generate(prompt: str, client: httpx.AsyncClient | None = None) -> str:
    """프롬프트를 OpenAI에 보내고 JSON 응답 텍스트만 반환한다."""

    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY 미설정으로 LLM 호출 불가")
        raise LLMClientError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

    payload: dict[str, Any] = {
        "model": settings.OPENAI_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You must return exactly one valid JSON object and no Markdown.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    async def _post_with_retry(active_client: httpx.AsyncClient) -> httpx.Response:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await active_client.post(
                    OPENAI_CHAT_COMPLETIONS_URL,
                    headers=headers,
                    json=payload,
                    timeout=DEFAULT_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if attempt == MAX_ATTEMPTS or exc.response.status_code < 500:
                    raise
            except httpx.HTTPError:
                if attempt == MAX_ATTEMPTS:
                    raise
            logger.warning(
                "LLM 호출 실패, %s초 후 재시도 (attempt=%s/%s)", RETRY_BACKOFF_SECONDS, attempt, MAX_ATTEMPTS
            )
            await asyncio.sleep(RETRY_BACKOFF_SECONDS)
        raise AssertionError("unreachable")  # pragma: no cover

    try:
        if client is None:
            async with httpx.AsyncClient() as active_client:
                response = await _post_with_retry(active_client)
        else:
            response = await _post_with_retry(client)
        data = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("LLM 호출 타임아웃: %s", exc)
        raise LLMClientError("LLM 호출 시간이 초과되었습니다.") from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        logger.warning("LLM HTTP 오류: status=%s detail=%s", exc.response.status_code, detail)
        raise LLMClientError(f"LLM HTTP 오류: {exc.response.status_code} {detail}") from exc
    except Exception as exc:  # pragma: no cover - defensive network/JSON path
        logger.warning("LLM 호출 실패: %s", exc)
        raise LLMClientError(f"LLM 호출 실패: {exc}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("LLM 응답 형식 오류: message.content 없음")
        raise LLMClientError("LLM 응답에서 message.content를 찾을 수 없습니다.") from exc

    if not isinstance(content, str) or not content.strip():
        logger.warning("LLM 응답이 비어 있음")
        raise LLMClientError("LLM 응답이 비어 있습니다.")

    return content
