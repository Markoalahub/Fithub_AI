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
    langchain_pipe_project: str = "fitai-pipeline-eval"
    langchain_meeting_project: str = "fitai-meeting-translation"
    langchain_tracing_enabled: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def init_langsmith():
    """Langsmith 트래킹 활성화 (파이프라인 + 회의록)"""
    import os
    settings = get_settings()

    if settings.langchain_tracing_enabled and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key

        # 기본값: 파이프라인 프로젝트
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_pipe_project

        print("=" * 50)
        print("✅ LangSmith 트래킹 활성화됨")
        print("=" * 50)
        print(f"🔗 API Key: {'설정됨' if settings.langchain_api_key else '미설정'}")
        print(f"📊 파이프라인 프로젝트: {settings.langchain_pipe_project}")
        print(f"💬 회의록 프로젝트: {settings.langchain_meeting_project}")
        print("=" * 50)
    else:
        print("⚠️  LangSmith 트래킹 비활성화됨")
        if not settings.langchain_api_key:
            print("  └─ LANGCHAIN_API_KEY 미설정")
