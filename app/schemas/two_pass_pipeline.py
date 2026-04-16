"""
2-Pass 파이프라인 생성 시스템 스키마

Pass 1 (Planner): PDF → PipelineDirection 리스트
Pass 2 (Builder): PipelineDirection → PipelineStepCreate 리스트
"""

from pydantic import BaseModel, Field
from typing import List


class PipelineDirection(BaseModel):
    """
    Pass 1 Planner가 생성하는 중간 데이터 구조
    Pass 2 Builder의 입력으로 사용됨
    """

    category: str = Field(
        ..., description="파이프라인 카테고리 (BE, FE, AI, DEVOPS, QA 등)"
    )
    goal: str = Field(..., description="파이프라인 목표 (1~2문장으로 명확하게)")
    priority: int = Field(..., ge=1, description="실행 우선순위 (1, 2, 3, ...)")
    tech_hint: str = Field(..., description="기술스택 힌트 (예: 'Spring Boot 3.x, JPA')")
    estimated_steps: int = Field(
        ..., ge=1, le=10, description="Builder가 생성할 PipelineStep 개수"
    )


class PlannerResponse(BaseModel):
    """
    Pass 1 Planner의 반환값
    PDF 분석 결과를 포함
    """

    directions: List[PipelineDirection] = Field(
        ..., description="도출된 파이프라인 방향성 목록"
    )
    total_count: int = Field(...., ge=0, description="Direction 총 개수")
    project_summary: str = Field(..., description="PDF에서 추출한 프로젝트 요약")
