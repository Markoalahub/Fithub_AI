from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.pipeline import router as pipeline_router

app = FastAPI(
    title="fitai — AI Pipeline Design Service",
    description=(
        "PRD(기획서)를 입력받아 LangGraph 기반 AI가 프로젝트 전체 파이프라인을 설계합니다.\n\n"
        "## 핵심 기능\n"
        "- PRD PDF + 요구사항 텍스트 → 파이프라인 아이템 목록 자동 생성\n"
        "- 각 아이템: 제목 / 내용 / 우선순위(HIGH·MEDIUM·LOW) / 세부 구현사항\n\n"
        "## LangGraph 워크플로우\n"
        "`PDF 파싱 → PRD 이해 → 도메인 식별 → 아이템 생성 → 우선순위 정렬`"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
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
app.include_router(pipeline_router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "fitai",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
