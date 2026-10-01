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

    # 정보나루는 하루 최대 500콜 제한이 있다. 대량 평가(예: 500권 테스트) 시
    # 책당 3콜(상세조회+키워드+이용분석) 대신 2콜(상세조회+키워드)만 쓰도록
    # 이용분석(co_loan_books) 호출을 건너뛰는 플래그. 653 필드의 공동대출
    # 근거만 빠지고 keywords/description 근거는 그대로 유지된다.
    D4L_SKIP_USAGE: bool = False

    # LLM API 키 (다음 단계)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-mini"
    GEMINI_API_KEY: str = ""


settings = Settings()
