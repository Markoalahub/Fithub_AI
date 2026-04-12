"""
Pipeline Service — CRUD + AI 파이프라인 생성 후 DB 저장
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from app.models.db.pipeline import Pipeline, PipelineStep
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineUpdate,
    PipelineStepCreate,
    PipelineStepUpdate,
)


# ──────────────────────────────────────────────
# Pipeline CRUD
# ──────────────────────────────────────────────

async def create_pipeline(
    db: AsyncSession, data: PipelineCreate
) -> Pipeline:
    """파이프라인 + 스텝 일괄 생성"""
    pipeline = Pipeline(
        project_id=data.project_id,
        category=data.category,
        version=data.version,
        is_active=data.is_active,
    )
    db.add(pipeline)
    await db.flush()  # id 확보

    if data.steps:
        for step_data in data.steps:
            step = PipelineStep(
                pipeline_id=pipeline.id,
                title=step_data.title,
                description=step_data.description,
                is_completed=step_data.is_completed,
                origin=step_data.origin,
            )
            db.add(step)

    await db.flush()
    # selectinload로 steps 함께 반환
    result = await db.execute(
        select(Pipeline)
        .options(selectinload(Pipeline.steps))
        .where(Pipeline.id == pipeline.id)
    )
    return result.scalar_one()


async def get_pipeline(db: AsyncSession, pipeline_id: int) -> Pipeline:
    """파이프라인 단건 조회"""
    result = await db.execute(
        select(Pipeline)
        .options(selectinload(Pipeline.steps))
        .where(Pipeline.id == pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise HTTPException(status_code=404, detail="파이프라인을 찾을 수 없습니다.")
    return pipeline


async def get_pipelines_by_project(
    db: AsyncSession, project_id: int
) -> List[Pipeline]:
    """프로젝트별 파이프라인 목록 조회"""
    result = await db.execute(
        select(Pipeline)
        .options(selectinload(Pipeline.steps))
        .where(Pipeline.project_id == project_id)
        .order_by(Pipeline.version.desc())
    )
    return list(result.scalars().all())


async def update_pipeline(
    db: AsyncSession, pipeline_id: int, data: PipelineUpdate
) -> Pipeline:
    """파이프라인 수정"""
    pipeline = await get_pipeline(db, pipeline_id)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pipeline, key, value)
    await db.flush()
    return pipeline


async def delete_pipeline(db: AsyncSession, pipeline_id: int) -> None:
    """파이프라인 삭제 (cascade → steps도 삭제)"""
    pipeline = await get_pipeline(db, pipeline_id)
    await db.delete(pipeline)
    await db.flush()


# ──────────────────────────────────────────────
# Pipeline Step CRUD
# ──────────────────────────────────────────────

async def create_pipeline_step(
    db: AsyncSession, pipeline_id: int, data: PipelineStepCreate
) -> PipelineStep:
    """파이프라인에 스텝 추가"""
    # 파이프라인 존재 확인
    await get_pipeline(db, pipeline_id)

    step = PipelineStep(
        pipeline_id=pipeline_id,
        title=data.title,
        description=data.description,
        is_completed=data.is_completed,
        origin=data.origin,
    )
    db.add(step)
    await db.flush()
    return step


async def get_pipeline_step(
    db: AsyncSession, step_id: int
) -> PipelineStep:
    """스텝 단건 조회"""
    result = await db.execute(
        select(PipelineStep).where(PipelineStep.id == step_id)
    )
    step = result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="파이프라인 스텝을 찾을 수 없습니다.")
    return step


async def update_pipeline_step(
    db: AsyncSession, step_id: int, data: PipelineStepUpdate
) -> PipelineStep:
    """스텝 수정"""
    step = await get_pipeline_step(db, step_id)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(step, key, value)
    await db.flush()
    return step


async def delete_pipeline_step(db: AsyncSession, step_id: int) -> None:
    """스텝 삭제"""
    step = await get_pipeline_step(db, step_id)
    await db.delete(step)
    await db.flush()


# ──────────────────────────────────────────────
# AI 파이프라인 → DB 저장
# ──────────────────────────────────────────────

async def save_ai_pipeline_to_db(
    db: AsyncSession,
    project_id: int,
    pipeline_items: list,
    category: Optional[str] = None,
) -> Pipeline:
    """
    LangGraph가 생성한 PipelineItem 리스트를 DB에 저장.
    - 같은 project_id + category의 기존 활성 파이프라인만 비활성화 (다른 직군은 유지)
    - 새 파이프라인 버전 생성
    """
    # 같은 category의 기존 active 파이프라인만 비활성화
    query = select(Pipeline).where(
        Pipeline.project_id == project_id,
        Pipeline.is_active == True,  # noqa: E712
    )
    if category:
        query = query.where(Pipeline.category == category)
    existing = await db.execute(query)
    for pipeline in existing.scalars().all():
        pipeline.is_active = False

    # 같은 category 내 최신 버전 번호 조회
    version_query = (
        select(Pipeline.version)
        .where(Pipeline.project_id == project_id)
    )
    if category:
        version_query = version_query.where(Pipeline.category == category)
    version_result = await db.execute(
        version_query.order_by(Pipeline.version.desc()).limit(1)
    )
    latest_version = version_result.scalar_one_or_none() or 0

    # 새 파이프라인 생성
    create_data = PipelineCreate(
        project_id=project_id,
        category=category,
        version=latest_version + 1,
        is_active=True,
        steps=[
            PipelineStepCreate(
                title=item.title,
                description="\n".join(item.details) if hasattr(item, "details") else None,
                is_completed=False,
                origin="ai_generated",
            )
            for item in pipeline_items
        ],
    )

    return await create_pipeline(db, create_data)
