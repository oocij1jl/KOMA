import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:  # pragma: no cover - import path depends on startup context
    from backend.routers import export, generate, lookup, validate
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    from routers import export, generate, lookup, validate

_SENSITIVE_QUERY_PATTERN = re.compile(r"(cert_key|authKey)=[^&\s\"]+", re.IGNORECASE)


class _RedactSensitiveQueryParams(logging.Filter):
    """httpx의 요청 로그(HTTP Request: ... URL ...)에서 국중도/정보나루 API 키를 마스킹한다."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and record.args:
            record.args = tuple(self._redact(arg) for arg in record.args)
        return True

    @staticmethod
    def _redact(value: object) -> object:
        text = str(value)
        if _SENSITIVE_QUERY_PATTERN.search(text):
            return _SENSITIVE_QUERY_PATTERN.sub(r"\1=***", text)
        return value


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").addFilter(_RedactSensitiveQueryParams())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
    """앱 생애주기 동안 재사용할 httpx.AsyncClient와 다건 생성 동시성 세마포어를
    생성/종료하고 request.state로 전달한다.

    세마포어를 요청마다 새로 만들지 않고 lifespan에서 한 번만 만들어 공유해야
    (1) 여러 bulk 요청이 겹쳐 들어와도 동시 LLM 호출 총량이 하나의 상한을
    넘지 않고, (2) asyncio 동기화 프리미티브가 실행 중인 이벤트 루프와 다른
    루프에서 재사용되어 RuntimeError가 나는 것도 함께 방지된다(httpx.AsyncClient와
    동일한 이유).
    """
    async with httpx.AsyncClient() as client:
        yield {
            "http_client": client,
            "generate_semaphore": asyncio.Semaphore(generate.GENERATE_BULK_CONCURRENCY),
        }


app = FastAPI(
    title="KOMA API",
    description="AI 기반 KORMARC 서지데이터 자동 생성 서비스",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중 전체 허용 (배포 시 프론트엔드 도메인으로 제한)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lookup.router, prefix="/api", tags=["lookup"])
app.include_router(generate.router, prefix="/api", tags=["generate"])
app.include_router(validate.router, prefix="/api", tags=["validate"])
app.include_router(export.router, prefix="/api", tags=["export"])


@app.get("/")
async def root():
    return {"message": "KOMA API 서버 정상 동작 중", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
