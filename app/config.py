from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    openai_api_key: str

    # Database — 기본값: sqlite+aiosqlite (로컬 개발)
    # 프로덕션: postgresql+asyncpg://user:pass@host/dbname
    database_url: str = "sqlite+aiosqlite:///./fitai.db"

    # Debug mode
    debug: bool = False

    # Langsmith 설정 (평가 & 트래킹)
    langchain_api_key: str = ""
    langchain_project: str = "fitai-pipeline-eval"
    langchain_tracing_enabled: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def init_langsmith():
    """Langsmith 트래킹 활성화"""
    import os
    settings = get_settings()

    if settings.langchain_tracing_enabled and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        print("✅ Langsmith 트래킹 활성화됨")
