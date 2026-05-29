from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import lookup, generate, validate

app = FastAPI(
    title="KOMA API",
    description="AI 기반 KORMARC 서지데이터 자동 생성 서비스",
    version="0.1.0",
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


@app.get("/")
async def root():
    return {"message": "KOMA API 서버 정상 동작 중", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}