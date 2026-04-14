from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.config import init_langsmith
from app.routers.pipeline import router as legacy_pipeline_router
from app.routers.pipeline_router import router as pipeline_router
from app.routers.meeting_router import router as meeting_router

# Langsmith 초기화
init_langsmith()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB 테이블 자동 생성"""
    # ORM 모델 import → Base.metadata에 등록
    import app.models.db  # noqa: F401
    await init_db()
    yield


app = FastAPI(
    title="fitai — AI Pipeline & Meeting Intelligence Service",
    description=(
        "PRD(기획서) 분석, AI 파이프라인 설계, 회의록 요약 및 맥락 변환을 제공하는 FastAPI 서비스.\n\n"
        "## 핵심 기능\n"
        "- **Pipeline**: PRD PDF → LangGraph 기반 파이프라인 자동 설계 → DB 저장\n"
        "- **Meeting**: 회의록 관리, AI 요약, 파이프라인 스텝 도출\n"
        "- **MSA 연동**: Spring Boot(Core API)의 project_id, user_id를 논리적 FK로 참조\n\n"
        "## LangGraph 워크플로우\n"
        "`PDF 파싱 → PRD 이해 → 도메인 식별 → 아이템 생성 → 우선순위 정렬`"
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(legacy_pipeline_router)  # 기존 /pipeline/generate (하위 호환)
app.include_router(pipeline_router)         # 신규 /pipelines/** CRUD
app.include_router(meeting_router)          # 신규 /meetings/** CRUD


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "fitai",
        "status": "running",
        "version": "0.2.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
