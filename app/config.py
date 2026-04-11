from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    openai_api_key: str

    # Database — 기본값: sqlite+aiosqlite (로컬 개발)
    # 프로덕션: postgresql+asyncpg://user:pass@host/dbname
    database_url: str = "sqlite+aiosqlite:///./fitai.db"

    # Debug mode
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
