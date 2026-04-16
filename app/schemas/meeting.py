"""
Pydantic v2 스키마: MeetingLog, MeetingAttendee, MeetingStepRelation

Request/Response DTO — ORM ↔ API 경계 분리
"""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
# Meeting Attendee
# ──────────────────────────────────────────────

class MeetingAttendeeCreate(BaseModel):
    """참석자 추가 요청"""
    user_id: int = Field(..., description="Logical FK → Spring DB: users.id")


class MeetingAttendeeResponse(BaseModel):
    """참석자 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_log_id: int
    user_id: int


# ──────────────────────────────────────────────
# Meeting ↔ Step Relation
# ──────────────────────────────────────────────

class MeetingStepRelationCreate(BaseModel):
    """회의록 ↔ 파이프라인 스텝 연결 요청"""
    pipeline_step_id: int = Field(..., description="연결할 pipeline_step ID")


class MeetingStepRelationResponse(BaseModel):
    """회의록 ↔ 파이프라인 스텝 연결 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_log_id: int
    pipeline_step_id: int


# ──────────────────────────────────────────────
# Meeting Log
# ──────────────────────────────────────────────

class MeetingLogCreate(BaseModel):
    """회의록 생성 요청"""
    project_id: int = Field(..., description="Logical FK → Spring DB: projects.id")
    content: str = Field(..., min_length=1, description="회의 원본 내용")
    meeting_log_content: Optional[str] = Field(
        None, description="(선택 사항) 스텝 조정 시 발생한 회의 기록"
    )
    ai_translated_explanation: Optional[str] = Field(
        None, description="기술 소통을 돕기 위해 AI가 변환한 설명 텍스트"
    )
    attendee_user_ids: Optional[List[int]] = Field(
        None, description="참석자 user_id 목록 (Logical FK → Spring DB)"
    )


class MeetingLogUpdate(BaseModel):
    """회의록 수정 요청"""
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    vector_id: Optional[str] = None
    meeting_log_content: Optional[str] = None
    ai_translated_explanation: Optional[str] = None


class MeetingLogResponse(BaseModel):
    """회의록 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    content: str
    summary: Optional[str] = None
    vector_id: Optional[str] = None
    meeting_log_content: Optional[str] = None
    ai_translated_explanation: Optional[str] = None
    created_at: datetime
    attendees: List[MeetingAttendeeResponse] = []
    step_relations: List[MeetingStepRelationResponse] = []

    # 번역 세션 관련 필드 (선택사항)
    is_translation_session: Optional[bool] = False
    conversation_type: Optional[str] = "meeting"
    translation_history: Optional[Dict[str, Any]] = None
    embedding: Optional[str] = None
    session_status: Optional[str] = "ongoing"


class MeetingLogListResponse(BaseModel):
    """회의록 목록 응답"""
    meetings: List[MeetingLogResponse]
    total: int


class MeetingSummarizeRequest(BaseModel):
    """AI 회의록 요약 요청"""
    meeting_log_id: int = Field(..., description="요약할 meeting_log ID")


class MeetingSummarizeResponse(BaseModel):
    """AI 회의록 요약 응답"""
    meeting_log_id: int
    summary: str
    derived_steps: List[str] = Field(
        default_factory=list,
        description="회의 내용에서 도출된 파이프라인 스텝 제안 목록",
    )
