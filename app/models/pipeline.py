from pydantic import BaseModel, Field
from enum import Enum
from typing import List


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PipelineItem(BaseModel):
    title: str = Field(..., description="파이프라인 아이템 제목")
    content: str = Field(..., description="해당 아이템의 목적 및 설명")
    priority: Priority = Field(..., description="AI가 판단한 우선순위")
    details: List[str] = Field(..., description="세부 구현사항 목록")


class PipelineGenerateResponse(BaseModel):
    pipeline: List[PipelineItem] = Field(..., description="설계된 파이프라인 아이템 목록")
    total_count: int = Field(..., description="파이프라인 아이템 수")
