from __future__ import annotations

from typing import Any

import httpx

try:  # pragma: no cover - import path depends on startup context
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from config import settings


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 45.0


class LLMClientError(RuntimeError):
    """LLM 호출 실패를 라우터/서비스 계층에서 구분하기 위한 예외."""


async def generate(prompt: str, client: httpx.AsyncClient | None = None) -> str:
    """프롬프트를 OpenAI에 보내고 JSON 응답 텍스트만 반환한다."""

    if not settings.OPENAI_API_KEY:
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

    async def _post(active_client: httpx.AsyncClient) -> httpx.Response:
        return await active_client.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers=headers,
            json=payload,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

    try:
        if client is None:
            async with httpx.AsyncClient() as active_client:
                response = await _post(active_client)
        else:
            response = await _post(client)
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as exc:
        raise LLMClientError("LLM 호출 시간이 초과되었습니다.") from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise LLMClientError(f"LLM HTTP 오류: {exc.response.status_code} {detail}") from exc
    except Exception as exc:  # pragma: no cover - defensive network/JSON path
        raise LLMClientError(f"LLM 호출 실패: {exc}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMClientError("LLM 응답에서 message.content를 찾을 수 없습니다.") from exc

    if not isinstance(content, str) or not content.strip():
        raise LLMClientError("LLM 응답이 비어 있습니다.")

    return content
