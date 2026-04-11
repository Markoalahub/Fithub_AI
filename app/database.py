"""
Database engine & session management (async SQLAlchemy)

- 로컬 개발: SQLite (aiosqlite)
- 프로덕션: PostgreSQL (asyncpg) — DATABASE_URL 환경변수로 전환
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스 클래스"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI Depends 용 DB 세션 제너레이터"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """앱 시작 시 테이블 자동 생성 (개발용)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
