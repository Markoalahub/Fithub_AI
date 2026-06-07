"""Project-scoped pipeline lookup APIs for Spring integration."""
from typing import Optional, Union

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.pipeline import (
    PipelineSummaryListResponse,
    PipelineSummaryResponse,
    PipelineV3Response,
)
from app.services import pipeline_service

router = APIRouter(prefix="/projects", tags=["Project Pipelines"])


@router.get(
    "/{project_id}/pipelines",
    response_model=Union[PipelineSummaryListResponse, PipelineV3Response],
    summary="프로젝트 파이프라인 조회",
)
async def get_project_pipelines(
    project_id: int,
    category: Optional[str] = Query(None, description="조회할 파이프라인 카테고리 (예: BE, FE, AI)"),
    db: AsyncSession = Depends(get_db),
):
    """
    category가 없으면 프로젝트 내 파이프라인 요약 목록을 반환하고,
    category가 있으면 해당 카테고리의 최신 파이프라인 1개를 반환합니다.
    """
    normalized_category = category.strip() if category is not None else None
    if not normalized_category:
        pipelines = await pipeline_service.get_pipeline_summaries_by_project(db, project_id)
        summaries = [
            PipelineSummaryResponse(
                pipe_id=pipeline.id,
                pipeline_name=f"{pipeline.category or 'UNKNOWN'} 파이프라인 {pipeline.id}",
                category=pipeline.category,
                github_repo_url=pipeline.github_repo_url,
            )
            for pipeline in pipelines
        ]
        return PipelineSummaryListResponse(
            project_id=project_id,
            pipelines=summaries,
            total=len(summaries),
        )

    pipeline = await pipeline_service.get_latest_pipeline_by_project_and_category(
        db,
        project_id,
        normalized_category,
    )
    return PipelineV3Response.model_validate(pipeline)
