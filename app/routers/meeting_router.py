"""
Meeting Router — REST API

엔드포인트:
  POST   /meetings/                              → 회의록 생성
  GET    /meetings/{id}                          → 회의록 단건 조회
  GET    /meetings/project/{project_id}          → 프로젝트별 회의록 목록
  PATCH  /meetings/{id}                          → 회의록 수정
  DELETE /meetings/{id}                          → 회의록 삭제

  POST   /meetings/{id}/attendees                → 참석자 추가
  DELETE /meetings/attendees/{attendee_id}       → 참석자 제거

  POST   /meetings/{id}/steps/{step_id}          → 회의 ↔ 스텝 연결
  DELETE /meetings/step-relations/{relation_id}  → 연결 해제

  POST   /meetings/{id}/summarize                → AI 회의록 요약
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.meeting import (
    MeetingLogCreate,
    MeetingLogUpdate,
    MeetingLogResponse,
    MeetingLogListResponse,
    MeetingAttendeeCreate,
    MeetingAttendeeResponse,
    MeetingStepRelationResponse,
    MeetingSummarizeResponse,
)
from app.services import meeting_service

router = APIRouter(prefix="/meetings", tags=["Meetings"])


# ──────────────────────────────────────────────
# Meeting Log CRUD
# ──────────────────────────────────────────────

@router.post(
    "/",
    response_model=MeetingLogResponse,
    status_code=201,
    summary="회의록 생성",
    description="회의록을 생성합니다. 참석자 user_id 목록을 함께 전달할 수 있습니다.",
)
async def create_meeting(
    data: MeetingLogCreate,
    db: AsyncSession = Depends(get_db),
):
    return await meeting_service.create_meeting_log(db, data)


@router.get(
    "/{meeting_id}",
    response_model=MeetingLogResponse,
    summary="회의록 단건 조회",
)
async def get_meeting(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await meeting_service.get_meeting_log(db, meeting_id)


@router.get(
    "/project/{project_id}",
    response_model=MeetingLogListResponse,
    summary="프로젝트별 회의록 목록",
)
async def get_meetings_by_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    meetings = await meeting_service.get_meeting_logs_by_project(db, project_id)
    return MeetingLogListResponse(meetings=meetings, total=len(meetings))


@router.patch(
    "/{meeting_id}",
    response_model=MeetingLogResponse,
    summary="회의록 수정",
)
async def update_meeting(
    meeting_id: int,
    data: MeetingLogUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await meeting_service.update_meeting_log(db, meeting_id, data)


@router.delete(
    "/{meeting_id}",
    status_code=204,
    summary="회의록 삭제",
)
async def delete_meeting(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
):
    await meeting_service.delete_meeting_log(db, meeting_id)


# ──────────────────────────────────────────────
# Meeting Attendee
# ──────────────────────────────────────────────

@router.post(
    "/{meeting_id}/attendees",
    response_model=MeetingAttendeeResponse,
    status_code=201,
    summary="회의 참석자 추가",
)
async def add_attendee(
    meeting_id: int,
    data: MeetingAttendeeCreate,
    db: AsyncSession = Depends(get_db),
):
    return await meeting_service.add_attendee(db, meeting_id, data.user_id)


@router.delete(
    "/attendees/{attendee_id}",
    status_code=204,
    summary="회의 참석자 제거",
)
async def remove_attendee(
    attendee_id: int,
    db: AsyncSession = Depends(get_db),
):
    await meeting_service.remove_attendee(db, attendee_id)


# ──────────────────────────────────────────────
# Meeting ↔ Step Relations
# ──────────────────────────────────────────────

@router.post(
    "/{meeting_id}/steps/{step_id}",
    response_model=MeetingStepRelationResponse,
    status_code=201,
    summary="회의록 ↔ 파이프라인 스텝 연결",
)
async def link_to_step(
    meeting_id: int,
    step_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await meeting_service.link_meeting_to_step(db, meeting_id, step_id)


@router.delete(
    "/step-relations/{relation_id}",
    status_code=204,
    summary="회의록 ↔ 스텝 연결 해제",
)
async def unlink_from_step(
    relation_id: int,
    db: AsyncSession = Depends(get_db),
):
    await meeting_service.unlink_meeting_from_step(db, relation_id)


# ──────────────────────────────────────────────
# AI 요약
# ──────────────────────────────────────────────

@router.post(
    "/{meeting_id}/summarize",
    response_model=MeetingSummarizeResponse,
    summary="AI 회의록 요약",
    description=(
        "GPT-4o로 회의록을 요약하고, 개발 파이프라인에 반영할 스텝을 도출합니다. "
        "요약 결과는 자동으로 DB에 저장됩니다."
    ),
)
async def summarize_meeting(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await meeting_service.summarize_meeting(db, meeting_id)
