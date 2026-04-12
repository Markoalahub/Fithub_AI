"""
Pydantic v2 스키마: Pipeline & PipelineStep

Request/Response DTO — ORM ↔ API 경계 분리
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


# ──────────────────────────────────────────────
# Pipeline Step
# ──────────────────────────────────────────────

class PipelineStepCreate(BaseModel):
    """파이프라인 스텝 생성 요청"""
    title: str = Field(..., max_length=255, description="스텝 제목")
    description: Optional[str] = Field(None, description="스텝 설명")
    is_completed: bool = Field(False, description="완료 여부")
    origin: Optional[str] = Field(
        None,
        max_length=50,
        description="생성 출처: ai_generated | user_created | meeting_derived",
    )


class PipelineStepUpdate(BaseModel):
    """파이프라인 스텝 수정 요청"""
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_completed: Optional[bool] = None
    origin: Optional[str] = Field(None, max_length=50)


class PipelineStepResponse(BaseModel):
    """파이프라인 스텝 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_id: int
    title: str
    description: Optional[str] = None
    is_completed: bool
    origin: Optional[str] = None


# ──────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────

class PipelineCreate(BaseModel):
    """파이프라인 생성 요청"""
    project_id: int = Field(..., description="Logical FK → Spring DB: projects.id")
    category: Optional[str] = Field(None, max_length=100, description="파이프라인 카테고리")
    version: int = Field(1, ge=1, description="버전")
    is_active: bool = Field(True, description="활성 여부")
    steps: Optional[List[PipelineStepCreate]] = Field(
        None, description="함께 생성할 스텝 목록 (선택)"
    )


class PipelineUpdate(BaseModel):
    """파이프라인 수정 요청"""
    category: Optional[str] = Field(None, max_length=100)
    version: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None


class PipelineResponse(BaseModel):
    """파이프라인 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    category: Optional[str] = None
    version: int
    is_active: bool
    steps: List[PipelineStepResponse] = []


class PipelineListResponse(BaseModel):
    """파이프라인 목록 응답"""
    pipelines: List[PipelineResponse]
    total: int


class PipelineGenerateRequest(BaseModel):
    """AI 파이프라인 생성 요청 (JSON body)"""
    project_id: int = Field(..., description="Spring DB project ID")
    requirements: str = Field(..., description="기획자 요구사항 텍스트")
    category: Optional[str] = Field(None, description="직군 카테고리 (FE, BE, AI 등)")
