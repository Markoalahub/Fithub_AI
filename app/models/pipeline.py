from pydantic import BaseModel, Field
from typing import List


class PipelineItem(BaseModel):
    title: str = Field(..., description="파이프라인 아이템 제목")
    priority: int = Field(..., description="진행 순서 (숫자가 작을수록 우선순위 높음, 예: 1, 2, 3...)")
    details: List[str] = Field(..., description="세부 구현사항 목록")
    duration: str = Field(default="", description="예상 소요 시간 (예: '2-3일', '1주')")
    tech_stack: str = Field(default="", description="기술스택 (예: 'Spring Boot 3.x', 'React 18')")


class PipelineGenerateResponse(BaseModel):
    pipeline: List[PipelineItem] = Field(..., description="설계된 파이프라인 아이템 목록")
    total_count: int = Field(..., description="파이프라인 아이템 수")
