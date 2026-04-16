"""
Pydantic v2 스키마: Pipeline & PipelineStep

Request/Response DTO — ORM ↔ API 경계 분리

요구사항:
- Step_Planner_Confirm_YN, Step_Developer_Confirm_YN 필수
- Step_Final_Confirmed_Status: 양측 모두 승인 시 'Confirmed'
- Step_Confirmation_Date: 양측 승인 완료 날짜
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime


# ──────────────────────────────────────────────
# Pipeline Step
# ──────────────────────────────────────────────

class PipelineStepCreate(BaseModel):
    """파이프라인 스텝 생성 요청"""
    step_task_description: str = Field(..., description="해당 스텝에서 수행할 구체적인 작업 상세 내용")
    step_sequence_number: int = Field(..., ge=1, description="파이프라인 내 작업 배치 순서")
    duration: Optional[str] = Field(None, max_length=100, description="예상 소요 시간 (예: '2-3일')")
    tech_stack: Optional[str] = Field(None, max_length=200, description="기술스택")
    origin: Optional[str] = Field(
        "user_created",
        max_length=50,
        description="생성 출처: ai_generated | user_created | meeting_derived",
    )


class PipelineStepConfirmation(BaseModel):
    """파이프라인 스텝 승인 요청"""
    step_planner_confirm_yn: str = Field(..., description="기획자 승인: Pending | Approved")
    step_developer_confirm_yn: str = Field(..., description="개발자 승인: Pending | Approved")


class PipelineStepUpdate(BaseModel):
    """파이프라인 스텝 수정 요청"""
    step_task_description: Optional[str] = None
    step_sequence_number: Optional[int] = Field(None, ge=1)
    step_github_status: Optional[str] = Field(None, description="Open | Closed")
    step_planner_confirm_yn: Optional[str] = None
    step_developer_confirm_yn: Optional[str] = None
    duration: Optional[str] = Field(None, max_length=100)
    tech_stack: Optional[str] = Field(None, max_length=200)
    origin: Optional[str] = Field(None, max_length=50)


class PipelineStepResponse(BaseModel):
    """파이프라인 스텝 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_id: int
    step_task_description: str
    step_sequence_number: int
    step_github_status: str
    step_planner_confirm_yn: str
    step_developer_confirm_yn: str
    step_confirmation_date: Optional[datetime] = None
    step_final_confirmed_status: str  # 계산 필드: Confirmed | Pending
    duration: Optional[str] = None
    tech_stack: Optional[str] = None
    origin: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────

class PipelineCreate(BaseModel):
    """파이프라인 생성 요청"""
    project_id: int = Field(..., description="Logical FK → Spring DB: projects.id")
    category: Optional[str] = Field(None, max_length=100, description="파이프라인 카테고리")
    version: int = Field(1, ge=1, description="버전")
    is_active: str = Field("Active", description="Active | Inactive")
    steps: Optional[List[PipelineStepCreate]] = Field(
        None, description="함께 생성할 스텝 목록 (선택)"
    )


class PipelineUpdate(BaseModel):
    """파이프라인 수정 요청"""
    category: Optional[str] = Field(None, max_length=100)
    version: Optional[int] = Field(None, ge=1)
    is_active: Optional[str] = None


class PipelineResponse(BaseModel):
    """파이프라인 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    category: Optional[str] = None
    version: int
    is_active: str
    steps: List[PipelineStepResponse] = []


class PipelineListResponse(BaseModel):
    """파이프라인 목록 응답"""
    pipelines: List[PipelineResponse]
    total: int
