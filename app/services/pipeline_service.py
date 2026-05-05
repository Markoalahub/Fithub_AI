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
        tech_stack=data.tech_stack,
    )
    db.add(pipeline)
    await db.flush()  # id 확보

    if data.steps:
        for step_data in data.steps:
            step = PipelineStep(
                pipeline_id=pipeline.id,
                step_task_description=step_data.step_task_description,
                step_sequence_number=step_data.step_sequence_number,
                category=step_data.category,
                priority=step_data.priority,
                deadline_date=step_data.deadline_date,
                deadline_time=step_data.deadline_time,
                tech_stack=step_data.tech_stack,
                depends_on=step_data.depends_on,
                origin=step_data.origin,
                step_details=step_data.step_details,
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
        step_task_description=data.step_task_description,
        step_details=data.step_details,
        category=data.category,
        step_sequence_number=data.step_sequence_number,
        priority=data.priority,
        deadline_date=data.deadline_date,
        deadline_time=data.deadline_time,
        tech_stack=data.tech_stack,
        depends_on=data.depends_on,
        origin=data.origin or "user_created",
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
    """스텝 수정 (승인 기반 제어 로직 포함)"""
    step = await get_pipeline_step(db, step_id)
    update_data = data.model_dump(exclude_unset=True)
 
    # 컨펌 관련 필드 이외의 필드가 포함되어 있는지 확인
    content_fields = {
        "step_task_description", "step_details", "step_sequence_number", 
        "deadline_date", "deadline_time", "tech_stack", "depends_on",
        "category", "priority", "duration"
    }
    is_updating_content = any(field in update_data for field in content_fields)
 
    # 내용 수정 시 승인 여부 체크 (기존 상태가 Confirmed여야 함)
    # 단, 컨펌 필드 자체를 업데이트하는 경우는 제외
    if is_updating_content:
        if step.step_planner_confirm_yn != "Approved" or step.step_developer_confirm_yn != "Approved":
            raise HTTPException(
                status_code=403, 
                detail="기획자와 개발자의 승인이 모두 완료(Approved)된 후에만 내용을 수정할 수 있습니다. 회의를 통해 먼저 컨펌해 주세요."
            )
 
    # 데이터 업데이트
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
    tech_stack: Optional[str] = None,
) -> Pipeline:
    """
    LangGraph가 생성한 PipelineItem 리스트를 DB에 저장.
    - 기존 활성 파이프라인을 비활성화
    - 새 파이프라인 버전 생성
    """
    # 기존 active 파이프라인 비활성화
    existing = await db.execute(
        select(Pipeline).where(
            Pipeline.project_id == project_id,
            Pipeline.is_active == "Active",
        )
    )
    for pipeline in existing.scalars().all():
        pipeline.is_active = "Inactive"

    # 최신 버전 번호 조회
    version_result = await db.execute(
        select(Pipeline.version)
        .where(Pipeline.project_id == project_id)
        .order_by(Pipeline.version.desc())
        .limit(1)
    )
    latest_version = version_result.scalar_one_or_none() or 0

    # 새 파이프라인 생성
    create_data = PipelineCreate(
        project_id=project_id,
        category=category,
        version=latest_version + 1,
        is_active="Active",
        tech_stack=tech_stack,
        steps=[
            PipelineStepCreate(
                step_task_description=item.get('title', '') if isinstance(item, dict) else getattr(item, 'title', ''),
                step_details=item.get('details', []) if isinstance(item, dict) else getattr(item, 'details', []),
                category=item.get('category', category) if isinstance(item, dict) else getattr(item, 'category', category),
                step_sequence_number=idx + 1,
                priority=max(1, min(2, getattr(item, "priority", 1) if hasattr(item, "__dict__") else item.get('priority', 1))),
                deadline_date=None,
                deadline_time=None,
                tech_stack=item.get('tech_stack', []) if isinstance(item, dict) else getattr(item, 'tech_stack', []),
                depends_on=item.get('depends_on', []) if isinstance(item, dict) else getattr(item, 'depends_on', []),
                origin="ai_generated",
            )
            for idx, item in enumerate(pipeline_items)
        ],
    )

    return await create_pipeline(db, create_data)
