"""
Meeting Service — CRUD + AI 요약 + 파이프라인 스텝 도출
"""
import json
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.models.db.meeting import (
    MeetingLog,
    MeetingAttendee,
    MeetingStepRelation,
)
from app.schemas.meeting import (
    MeetingLogCreate,
    MeetingLogUpdate,
    MeetingSummarizeResponse,
)
from app.config import get_settings


def _get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0.3,
        api_key=settings.openai_api_key,
    )


# ──────────────────────────────────────────────
# Meeting Log CRUD
# ──────────────────────────────────────────────

async def create_meeting_log(
    db: AsyncSession, data: MeetingLogCreate
) -> MeetingLog:
    """회의록 생성 (참석자 매핑 포함)"""
    meeting = MeetingLog(
        project_id=data.project_id,
        content=data.content,
    )
    db.add(meeting)
    await db.flush()

    # 참석자 매핑
    if data.attendee_user_ids:
        for user_id in data.attendee_user_ids:
            attendee = MeetingAttendee(
                meeting_log_id=meeting.id,
                user_id=user_id,
            )
            db.add(attendee)

    await db.flush()

    result = await db.execute(
        select(MeetingLog)
        .options(
            selectinload(MeetingLog.attendees),
            selectinload(MeetingLog.step_relations),
        )
        .where(MeetingLog.id == meeting.id)
    )
    return result.scalar_one()


async def get_meeting_log(db: AsyncSession, meeting_id: int) -> MeetingLog:
    """회의록 단건 조회"""
    result = await db.execute(
        select(MeetingLog)
        .options(
            selectinload(MeetingLog.attendees),
            selectinload(MeetingLog.step_relations),
        )
        .where(MeetingLog.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return meeting


async def get_meeting_logs_by_project(
    db: AsyncSession, project_id: int
) -> List[MeetingLog]:
    """프로젝트별 회의록 목록 조회"""
    result = await db.execute(
        select(MeetingLog)
        .options(
            selectinload(MeetingLog.attendees),
            selectinload(MeetingLog.step_relations),
        )
        .where(MeetingLog.project_id == project_id)
        .order_by(MeetingLog.created_at.desc())
    )
    return list(result.scalars().all())


async def update_meeting_log(
    db: AsyncSession, meeting_id: int, data: MeetingLogUpdate
) -> MeetingLog:
    """회의록 수정"""
    meeting = await get_meeting_log(db, meeting_id)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(meeting, key, value)
    await db.flush()
    return meeting


async def delete_meeting_log(db: AsyncSession, meeting_id: int) -> None:
    """회의록 삭제 (cascade → attendees, step_relations도 삭제)"""
    meeting = await get_meeting_log(db, meeting_id)
    await db.delete(meeting)
    await db.flush()


# ──────────────────────────────────────────────
# Meeting Attendee 관리
# ──────────────────────────────────────────────

async def add_attendee(
    db: AsyncSession, meeting_id: int, user_id: int
) -> MeetingAttendee:
    """참석자 추가"""
    await get_meeting_log(db, meeting_id)  # 존재 확인
    attendee = MeetingAttendee(
        meeting_log_id=meeting_id,
        user_id=user_id,
    )
    db.add(attendee)
    await db.flush()
    return attendee


async def remove_attendee(db: AsyncSession, attendee_id: int) -> None:
    """참석자 제거"""
    result = await db.execute(
        select(MeetingAttendee).where(MeetingAttendee.id == attendee_id)
    )
    attendee = result.scalar_one_or_none()
    if attendee is None:
        raise HTTPException(status_code=404, detail="참석자를 찾을 수 없습니다.")
    await db.delete(attendee)
    await db.flush()


# ──────────────────────────────────────────────
# Meeting ↔ Step 관계 관리
# ──────────────────────────────────────────────

async def link_meeting_to_step(
    db: AsyncSession, meeting_id: int, step_id: int
) -> MeetingStepRelation:
    """회의록과 파이프라인 스텝 연결"""
    relation = MeetingStepRelation(
        meeting_log_id=meeting_id,
        pipeline_step_id=step_id,
    )
    db.add(relation)
    await db.flush()
    return relation


async def unlink_meeting_from_step(
    db: AsyncSession, relation_id: int
) -> None:
    """회의록 ↔ 스텝 연결 해제"""
    result = await db.execute(
        select(MeetingStepRelation).where(MeetingStepRelation.id == relation_id)
    )
    relation = result.scalar_one_or_none()
    if relation is None:
        raise HTTPException(status_code=404, detail="연결 관계를 찾을 수 없습니다.")
    await db.delete(relation)
    await db.flush()


# ──────────────────────────────────────────────
# AI 회의록 요약 + 파이프라인 스텝 도출
# ──────────────────────────────────────────────

async def summarize_meeting(
    db: AsyncSession, meeting_id: int
) -> MeetingSummarizeResponse:
    """
    GPT-4o를 사용하여:
    1. 회의록 내용을 요약
    2. 개발 관련 파이프라인 스텝을 도출
    3. 요약 결과를 DB에 저장
    """
    meeting = await get_meeting_log(db, meeting_id)
    llm = _get_llm()

    messages = [
        SystemMessage(content=(
            "당신은 시니어 프로젝트 매니저입니다. "
            "회의록을 분석하여 두 가지를 수행합니다:\n"
            "1. 회의 내용을 간결하게 요약 (핵심 결정사항, 액션 아이템 중심)\n"
            "2. 회의 내용에서 개발 파이프라인에 반영해야 할 신규 스텝을 도출\n\n"
            "반드시 아래 JSON 형식으로만 응답하세요:\n"
            '{\n'
            '  "summary": "회의 요약 텍스트",\n'
            '  "derived_steps": [\n'
            '    "도출된 스텝 1",\n'
            '    "도출된 스텝 2"\n'
            '  ]\n'
            '}\n\n'
            "derived_steps가 없으면 빈 배열로 응답하세요."
        )),
        HumanMessage(content=(
            f"## 회의록 내용\n{meeting.content}"
        )),
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    # JSON 파싱 (코드블록 제거)
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                content = stripped[4:].strip()
                break
            elif stripped.startswith("{"):
                content = stripped
                break

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # 파싱 실패 → 원본 텍스트를 요약으로 사용
        parsed = {"summary": content, "derived_steps": []}

    summary_text = parsed.get("summary", content)
    derived_steps = parsed.get("derived_steps", [])

    # DB에 요약 저장
    meeting.summary = summary_text
    await db.flush()

    return MeetingSummarizeResponse(
        meeting_log_id=meeting.id,
        summary=summary_text,
        derived_steps=derived_steps,
    )
