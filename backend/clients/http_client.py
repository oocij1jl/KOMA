from __future__ import annotations

import httpx
from fastapi import Request


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """lifespan이 request.state에 넣어둔 공유 httpx.AsyncClient를 반환한다.

    클라이언트의 생성·종료는 backend/main.py의 lifespan이 전담한다. 이 함수는
    lifespan state에서 꺼내 라우터에 주입(Depends)하는 역할만 한다.
    """
    return request.state.http_client
