"""
환경변수 설정 관리.
.env 파일 또는 시스템 환경변수에서 로드.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 국립중앙도서관 Open API 인증키
    NL_API_KEY: str = ""

    # 도서관 정보나루 API 인증키
    D4L_API_KEY: str = ""

    # LLM API 키 (다음 단계)
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()