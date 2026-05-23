"""
Pydantic v2 스키마: Pipeline & PipelineStep

Request/Response DTO — ORM ↔ API 경계 분리

요구사항:
- Step_Planner_Confirm_YN, Step_Developer_Confirm_YN 필수
- Step_Final_Confirmed_Status: 양측 모두 승인 시 'Confirmed'
- Step_Confirmation_Date: 양측 승인 완료 날짜
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, List, Optional
from datetime import datetime, date, time


# ──────────────────────────────────────────────
# Pipeline Step
# ──────────────────────────────────────────────

class PipelineStepCreate(BaseModel):
    """파이프라인 스텝 생성 요청"""
    step_task_description: str = Field(..., description="해당 스텝의 요약 설명")
    step_details: Optional[List[str]] = Field(None, description="상세 작업 리스트")
    category: Optional[str] = Field(None, description="BE | FE | DB | INFRA | AI")
    step_sequence_number: int = Field(..., ge=1, description="파이프라인 내 작업 배치 순서")
    priority: int = Field(1, ge=1, le=2, description="1: 핵심, 2: 부가")
    deadline_date: Optional[date] = Field(None, description="마감 날짜")
    deadline_time: Optional[time] = Field(None, description="마감 시간")
    tech_stack: Optional[List[str]] = Field(None, description="기술 스택 리스트 (GitHub 라벨용)")
    depends_on: Optional[List[int]] = Field(default_factory=list, description="선행 작업 sequence_number 리스트")
    origin: Optional[str] = Field(None, max_length=50, description="출처")


class PipelineStepConfirmation(BaseModel):
    """파이프라인 스텝 승인 요청 (직접 입력 방식 - 레거시)"""
    step_planner_confirm_yn: str = Field(..., description="기획자 승인: Pending | Approved")
    step_developer_confirm_yn: str = Field(..., description="개발자 승인: Pending | Approved")


class MeetingStepConfirmation(BaseModel):
    """회의 기반 파이프라인 스텝 최종 승인 요청"""
    meeting_id: int = Field(..., description="상태를 확인할 회의(MeetingLog)의 PK")


class PipelineStepUpdate(BaseModel):
    """파이프라인 스텝 수정 요청"""
    step_task_description: Optional[str] = None
    step_details: Optional[List[str]] = None
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
    step_details: Optional[List[str]] = None
    category: Optional[str] = None
    step_sequence_number: int
    priority: int
    deadline_date: Optional[date] = None
    deadline_time: Optional[time] = None
    tech_stack: Optional[List[str]] = None
    depends_on: Optional[List[int]] = None
    step_github_status: str
    step_planner_confirm_yn: str
    step_developer_confirm_yn: str
    step_confirmation_date: Optional[datetime] = None
    step_final_confirmed_status: str  # 계산 필드: Confirmed | Pending
    duration: Optional[str] = None
    tech_stack: Optional[str] = None
    origin: Optional[str] = None
    priority: int
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
    tech_stack: Optional[str] = Field(None, max_length=200, description="기술 스택")
    steps: Optional[List[PipelineStepCreate]] = Field(
        None, description="함께 생성할 스텝 목록 (선택)"
    )


class PipelineUpdate(BaseModel):
    """파이프라인 수정 요청"""
    category: Optional[str] = Field(None, max_length=100)
    version: Optional[int] = Field(None, ge=1)
    is_active: Optional[str] = None
    tech_stack: Optional[str] = None


class PipelineResponse(BaseModel):
    """파이프라인 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    category: Optional[str] = None
    version: int
    is_active: str
    tech_stack: Optional[str] = None
    steps: List[PipelineStepResponse] = []


class PipelineListResponse(BaseModel):
    """파이프라인 목록 응답"""
    pipelines: List[PipelineResponse]
    total: int


# ──────────────────────────────────────────────
# V3 Specialized (Slim)
# ──────────────────────────────────────────────

class PipelineFeatV3Response(BaseModel):
    """V3 최적화 스텝(Feat) 응답 (불필요한 필드 제거)"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    feat_id: int = Field(validation_alias="id")
    feat_title: str = Field(validation_alias="step_task_description")
    feat_details: Optional[List[str]] = Field(None, validation_alias="step_details")
    priority: int


class PipelineV3Response(BaseModel):
    """V3 최적화 파이프라인 응답 (불필요한 필드 제거)"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    pipe_id: int = Field(validation_alias="id")
    project_id: int
    category: Optional[str] = None
    version: int
    tech_stack: Optional[str] = None
    feats: List[PipelineFeatV3Response] = Field(default_factory=list, validation_alias="steps")


# ──────────────────────────────────────────────
# V4 Multi-Agent Response
# ──────────────────────────────────────────────

class V4StepItem(BaseModel):
    """V4 개별 스텝 (BE/FE 공통)"""
    title: str
    details: List[str] = []
    category: Optional[str] = None
    priority: int = 1
    tech_stack: List[str] = []
    depends_on: List[Any] = []

class V4WireframeItem(BaseModel):
    """V4 ASCII 와이어프레임"""
    screen_id: str = ""
    screen_name: str = ""
    ascii_wireframe: str = ""
    related_flow_nodes: str = ""

class V4ComponentItem(BaseModel):
    """V4 컴포넌트 트리 항목"""
    screen_id: str = ""
    name: str = ""
    type: str = ""
    children: List[str] = []

class PipelineV4Response(BaseModel):
    """V4 Multi-Agent 파이프라인 전체 응답"""
    model_config = ConfigDict(from_attributes=True)

    # DB 저장된 파이프라인 (기존 호환)
    id: int
    project_id: int
    category: Optional[str] = None
    version: int
    tech_stack: Optional[str] = None
    steps: List[PipelineFeatV3Response] = []

    # V4 추가 메타데이터
    user_flow: Optional[dict] = None
    user_flow_mermaid: Optional[str] = None
    wireframes: List[V4WireframeItem] = []
    component_tree: List[V4ComponentItem] = []
    be_steps: List[V4StepItem] = []
    fe_steps: List[V4StepItem] = []
    validation_logs: List[str] = []
