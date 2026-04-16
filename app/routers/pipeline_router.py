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

  POST   /pipelines/generate-and-save   → AI 생성 + DB 저장 (기본)
  POST   /pipelines/generate-2pass      → 2-Pass AI 생성 + DB 저장
"""
import logging
import tempfile
import os
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from docling.document_converter import DocumentConverter

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
from app.services import two_pass_pipeline_service
from app.graph.pipeline_graph import pipeline_graph

logger = logging.getLogger(__name__)

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
            "category": category or "BE",
            "parsed_text": "",
            "prd_summary": "",
            "domains": [],
            "framework": None,
            "template_stages": None,
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


# ──────────────────────────────────────────────
# 2-Pass AI Pipeline Generation
# ──────────────────────────────────────────────


@router.post(
    "/generate-2pass",
    response_model=PipelineListResponse,
    summary="2-Pass AI 파이프라인 생성 → DB 저장",
    description=(
        "2-Pass 시스템으로 AI 파이프라인을 생성하고 DB에 저장합니다.\n\n"
        "**Pass 1 (Planner)**: gpt-4o로 PDF 분석 → 파이프라인 방향성(Direction) 도출\n"
        "**Pass 2 (Builder)**: gpt-4o-mini로 각 Direction을 병렬 처리 → 구체적 스텝 생성\n\n"
        "결과: 프로젝트별로 여러 파이프라인 생성 (BE, FE, AI, DevOps 등)"
    ),
)
async def generate_2pass_pipeline(
    project_id: int = Form(..., description="Spring DB의 project ID (Logical FK)"),
    requirements: str = Form(..., description="기획자 요구사항 텍스트"),
    category: Optional[str] = Form(
        None, description="특정 카테고리만 생성 (예: 'BE'). None이면 모든 카테고리"
    ),
    prd_file: Optional[UploadFile] = File(None, description="PRD PDF 파일 (선택)"),
    db: AsyncSession = Depends(get_db),
):
    """
    2-Pass 파이프라인 생성 및 DB 저장

    1. PDF 파싱 (Docling)
    2. Pass 1 (Planner): PDF 분석 → Direction 도출
    3. Pass 2 (Builder): Direction 병렬 처리 → Step 생성
    4. PipelineCreate 조립 → DB 저장
    5. 결과 반환
    """
    # PDF 파싱
    pdf_text = ""
    if prd_file is not None:
        if not prd_file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

        # PDF 바이트 읽기
        pdf_bytes = await prd_file.read()

        # 임시 파일로 저장하여 Docling 처리
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            pdf_text = result.document.export_to_markdown()
            logger.info(f"PDF 파싱 완료: {len(pdf_text)} 문자")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF 파싱 실패: {str(e)}")
        finally:
            os.unlink(tmp_path)

    # 2-Pass 파이프라인 생성
    try:
        pipelines_create = await two_pass_pipeline_service.generate_pipeline_from_pdf(
            project_id=project_id,
            pdf_text=pdf_text,
            category=category,
        )
        logger.info(f"2-Pass 파이프라인 생성 완료: {len(pipelines_create)}개 파이프라인")
    except Exception as e:
        logger.error(f"2-Pass 파이프라인 생성 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"2-Pass 파이프라인 생성 중 오류: {str(e)}",
        )

    if not pipelines_create:
        raise HTTPException(
            status_code=500,
            detail="2-Pass AI가 파이프라인을 생성하지 못했습니다.",
        )

    # DB 저장
    saved_pipelines = []
    for pipeline_create in pipelines_create:
        try:
            pipeline = await pipeline_service.save_ai_pipeline_to_db(
                db=db,
                project_id=project_id,
                pipeline_items=[
                    {
                        "title": step.title,
                        "priority": idx + 1,
                        "details": step.description.split("\n")
                        if step.description
                        else [],
                        "duration": step.duration or "",
                        "tech_stack": step.tech_stack or "",
                    }
                    for idx, step in enumerate(pipeline_create.steps or [])
                ],
                category=pipeline_create.category,
            )
            saved_pipelines.append(pipeline)
            logger.info(
                f"파이프라인 DB 저장: {pipeline_create.category} (v{pipeline.version})"
            )
        except Exception as e:
            logger.error(
                f"파이프라인 DB 저장 실패 ({pipeline_create.category}): {e}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"파이프라인 DB 저장 실패: {str(e)}",
            )

    return PipelineListResponse(
        pipelines=saved_pipelines,
        total=len(saved_pipelines),
    )
