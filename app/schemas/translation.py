"""
번역 API 스키마
- 기획자 → 개발자 번역 요청/응답
- 개발자 → 기획자 번역 요청/응답
- 번역 세션 종료 요청/응답
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TechnicalTranslation(BaseModel):
    """기획자 → 개발자 번역 결과"""

    problem_statement: str = Field(
        ..., description="핵심 문제를 기술 용어로 표현"
    )
    technical_approach: List[str] = Field(
        ..., description="구체적인 구현 방식 (3-5개 항목)"
    )
    tech_stack: List[str] = Field(..., description="필요한 기술 스택")
    effort_estimate: str = Field(..., description="예상 개발 기간 (예: 3-5일)")
    dependencies: List[str] = Field(
        default_factory=list, description="선행 작업 또는 확인 사항"
    )


class TranslateToTechnicalRequest(BaseModel):
    """기획자 → 개발자 번역 요청"""

    original_statement: str = Field(..., description="기획자의 원본 질문/요구사항")
    context: Optional[str] = Field(default=None, description="추가 컨텍스트")


class TranslateToTechnicalResponse(BaseModel):
    """기획자 → 개발자 번역 응답"""

    meeting_id: int
    original_statement: str
    ai_translation: TechnicalTranslation
    saved_at: datetime


class PlanningTranslation(BaseModel):
    """개발자 → 기획자 번역 결과"""

    simple_explanation: str = Field(
        ..., description="한 문장 요약 (초등학생도 이해 가능)"
    )
    analogy: str = Field(..., description="실생활 비유")
    impact: str = Field(
        ..., description="비즈니스 영향도 (사용자 경험, 비용, 속도 등)"
    )
    timeline: str = Field(..., description="예상 소요 시간")
    why_needed: str = Field(..., description="왜 이 작업이 필요한지 (기획자 관점)")


class TranslateToPlanningRequest(BaseModel):
    """개발자 → 기획자 번역 요청"""

    developer_statement: str = Field(..., description="개발자의 원본 설명")
    original_audience: str = Field(
        default="developer", description="원래 대상 (developer/planner)"
    )
    context: Optional[str] = Field(default=None, description="추가 컨텍스트")


class TranslateToPlanningResponse(BaseModel):
    """개발자 → 기획자 번역 응답"""

    meeting_id: int
    original_statement: str
    ai_translation: PlanningTranslation
    saved_at: datetime


class TranslationMessage(BaseModel):
    """번역 대화의 한 메시지"""

    role: str = Field(..., description="role: 'planner' | 'developer'")
    original: str = Field(..., description="원본 텍스트")
    ai_translation: Dict[str, Any] = Field(..., description="AI 번역 결과 (JSON)")
    target_audience: str = Field(
        ..., description="번역 대상: 'developer' | 'planner'"
    )
    timestamp: datetime


class SessionSummary(BaseModel):
    """번역 세션 최종 요약"""

    meeting_id: int
    session_summary: str = Field(..., description="전체 대화 요약")
    key_agreements: List[str] = Field(
        default_factory=list, description="합의된 사항들"
    )
    next_steps: List[str] = Field(
        default_factory=list, description="다음 단계 (액션 아이템)"
    )
    embedding_id: Optional[str] = Field(
        default=None, description="임베딩 벡터 ID"
    )
    session_status: str = Field(default="completed", description="세션 상태")
    created_at: datetime


class FinalizationResponse(BaseModel):
    """번역 세션 종료 응답"""

    meeting_id: int
    session_summary: str
    key_agreements: List[str]
    next_steps: List[str]
    embedding_id: Optional[str]
    session_status: str
    saved_at: datetime


class TranslationSearchResult(BaseModel):
    """번역 검색 결과"""

    meeting_id: int
    summary: str
    session_date: datetime
    relevance_score: float = Field(..., description="0.0 ~ 1.0 범위의 유사도 점수")
    conversation_type: str


class TranslationSearchResponse(BaseModel):
    """번역 검색 응답"""

    query: str
    total_results: int
    results: List[TranslationSearchResult]
    search_time_ms: float
