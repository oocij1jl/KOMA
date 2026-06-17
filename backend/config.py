"""
환경변수 설정 관리.
.env 파일 또는 시스템 환경변수에서 로드.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8")

    # 국립중앙도서관 Open API 인증키
    NL_API_KEY: str = ""

    # 도서관 정보나루 API 인증키
    D4L_API_KEY: str = ""

    # LLM API 키 (다음 단계)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-mini"
    GEMINI_API_KEY: str = ""


settings = Settings()
