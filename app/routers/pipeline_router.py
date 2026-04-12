"""
Pipeline Router — REST API

엔드포인트:
  POST   /pipelines/             → 파이프라인 생성
  GET    /pipelines/{id}         → 파이프라인 단건 조회
  GET    /pipelines/project/{id} → 프로젝트별 파이프라인 목록
  PATCH  /pipelines/{id}         → 파이프라인 수정
  DELETE /pipelines/{id}         → 파이프라인 삭제

  POST   /pipelines/{id}/steps          → 스텝 추가
  PATCH  /pipelines/steps/{step_id}     → 스텝 수정
  DELETE /pipelines/steps/{step_id}     → 스텝 삭제

  POST   /pipelines/generate-and-save   → AI 생성 + DB 저장
"""
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineUpdate,
    PipelineResponse,
    PipelineListResponse,
    PipelineStepCreate,
    PipelineStepUpdate,
    PipelineStepResponse,
)
from app.services import pipeline_service
from app.graph.pipeline_graph import pipeline_graph

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


# ──────────────────────────────────────────────
# Pipeline CRUD
# ──────────────────────────────────────────────

@router.post(
    "/",
    response_model=PipelineResponse,
    status_code=201,
    summary="파이프라인 생성",
)
async def create_pipeline(
    data: PipelineCreate,
    db: AsyncSession = Depends(get_db),
):
    pipeline = await pipeline_service.create_pipeline(db, data)
    return pipeline


@router.get(
    "/{pipeline_id}",
    response_model=PipelineResponse,
    summary="파이프라인 단건 조회",
)
async def get_pipeline(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.get_pipeline(db, pipeline_id)


@router.get(
    "/project/{project_id}",
    response_model=PipelineListResponse,
    summary="프로젝트별 파이프라인 목록",
)
async def get_pipelines_by_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    pipelines = await pipeline_service.get_pipelines_by_project(db, project_id)
    return PipelineListResponse(pipelines=pipelines, total=len(pipelines))


@router.patch(
    "/{pipeline_id}",
    response_model=PipelineResponse,
    summary="파이프라인 수정",
)
async def update_pipeline(
    pipeline_id: int,
    data: PipelineUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.update_pipeline(db, pipeline_id, data)


@router.delete(
    "/{pipeline_id}",
    status_code=204,
    summary="파이프라인 삭제",
)
async def delete_pipeline(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
):
    await pipeline_service.delete_pipeline(db, pipeline_id)


# ──────────────────────────────────────────────
# Pipeline Step CRUD
# ──────────────────────────────────────────────

@router.post(
    "/{pipeline_id}/steps",
    response_model=PipelineStepResponse,
    status_code=201,
    summary="파이프라인에 스텝 추가",
)
async def create_step(
    pipeline_id: int,
    data: PipelineStepCreate,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.create_pipeline_step(db, pipeline_id, data)


@router.patch(
    "/steps/{step_id}",
    response_model=PipelineStepResponse,
    summary="파이프라인 스텝 수정",
)
async def update_step(
    step_id: int,
    data: PipelineStepUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.update_pipeline_step(db, step_id, data)


@router.delete(
    "/steps/{step_id}",
    status_code=204,
    summary="파이프라인 스텝 삭제",
)
async def delete_step(
    step_id: int,
    db: AsyncSession = Depends(get_db),
):
    await pipeline_service.delete_pipeline_step(db, step_id)


# ──────────────────────────────────────────────
# AI Generate + DB Save (기존 /pipeline/generate 확장)
# ──────────────────────────────────────────────

@router.post(
    "/generate-and-save",
    response_model=PipelineResponse,
    summary="AI 파이프라인 생성 → DB 저장",
    description=(
        "PRD PDF + 요구사항 텍스트로 LangGraph AI 파이프라인을 생성하고 "
        "결과를 DB에 저장합니다. 기존 활성 파이프라인은 비활성화됩니다."
    ),
)
async def generate_and_save_pipeline(
    project_id: int = Form(..., description="Spring DB의 project ID (Logical FK)"),
    requirements: str = Form(..., description="기획자 요구사항 텍스트"),
    category: Optional[str] = Form(None, description="파이프라인 카테고리"),
    prd_file: Optional[UploadFile] = File(None, description="PRD PDF 파일 (선택)"),
    db: AsyncSession = Depends(get_db),
):
    # PDF 바이트 읽기
    pdf_bytes: Optional[bytes] = None
    if prd_file is not None:
        if not prd_file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")
        pdf_bytes = await prd_file.read()

    # LangGraph 실행
    try:
        result = await pipeline_graph.ainvoke({
            "requirements": requirements,
            "pdf_bytes": pdf_bytes,
            "parsed_text": "",
            "prd_summary": "",
            "domains": [],
            "raw_items": "",
            "pipeline": [],
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 파이프라인 생성 중 오류: {str(e)}",
        )

    pipeline_items = result.get("pipeline", [])
    if not pipeline_items:
        raise HTTPException(
            status_code=500,
            detail="AI가 파이프라인 아이템을 생성하지 못했습니다.",
        )

    # DB 저장
    pipeline = await pipeline_service.save_ai_pipeline_to_db(
        db, project_id, pipeline_items, category
    )
    return pipeline
