"""
Pydantic v2 스키마: UserFlow, UserFlowNode, UserFlowEdge

Request/Response DTO — ORM ↔ API 경계 분리
"""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


# ──────────────────────────────────────────────
# UserFlow Node
# ──────────────────────────────────────────────

class UserFlowNodeCreate(BaseModel):
    """유저 플로우 노드 추가 요청"""
    name: str = Field(..., min_length=1, max_length=200, description="기능명 (로그인, 홈 화면 등)")
    description: Optional[str] = Field(None, description="기능 상세 설명")
    node_type: str = Field("screen", description="screen | process | decision")
    sequence_order: int = Field(0, ge=0, description="표시 순서")


class UserFlowNodeUpdate(BaseModel):
    """유저 플로우 노드 수정 요청"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    node_type: Optional[str] = Field(None, description="screen | process | decision")
    sequence_order: Optional[int] = Field(None, ge=0)


class UserFlowNodeResponse(BaseModel):
    """유저 플로우 노드 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_flow_id: int
    name: str
    description: Optional[str] = None
    node_type: str
    wireframe_ascii: Optional[str] = None
    sequence_order: int
    created_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# UserFlow Edge
# ──────────────────────────────────────────────

class UserFlowEdgeCreate(BaseModel):
    """유저 플로우 엣지(연결) 추가 요청"""
    from_node_id: int = Field(..., description="출발 노드 ID")
    to_node_id: int = Field(..., description="도착 노드 ID")
    label: Optional[str] = Field(None, max_length=200, description="연결 조건/설명")


class UserFlowEdgeResponse(BaseModel):
    """유저 플로우 엣지 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_flow_id: int
    from_node_id: int
    to_node_id: int
    label: Optional[str] = None
    created_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# UserFlow (Root)
# ──────────────────────────────────────────────

class UserFlowResponse(BaseModel):
    """유저 플로우 전체 응답 (nodes + edges 포함)"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: Optional[str] = None
    prd_context: Optional[str] = None
    session_status: Optional[str] = None
    current_turn: Optional[int] = None
    created_at: Optional[datetime] = None
    nodes: List[UserFlowNodeResponse] = []
    edges: List[UserFlowEdgeResponse] = []


class UserFlowListResponse(BaseModel):
    """유저 플로우 목록 응답"""
    user_flows: List[UserFlowResponse]
    total: int


# ──────────────────────────────────────────────
# Stage Request DTOs
# ──────────────────────────────────────────────

class GenerateWireframeRequest(BaseModel):
    """Stage 2: 와이어프레임 생성 요청"""
    user_flow_id: int = Field(..., description="Stage 1에서 생성된 유저 플로우 ID")


class GeneratePipelineFromFlowRequest(BaseModel):
    """Stage 3: 유저 플로우 기반 파이프라인 생성 요청"""
    user_flow_id: int = Field(..., description="유저 플로우 ID")
    project_id: int = Field(..., description="Spring DB의 project ID (Logical FK)")
    category: Optional[str] = Field(None, description="파이프라인 카테고리 (BE, FE 등)")
    tech_stack: Optional[str] = Field(None, description="기술 스택 (예: Spring Boot, JPA)")


# ──────────────────────────────────────────────
# Interview Session DTOs
# ──────────────────────────────────────────────

class InterviewMessage(BaseModel):
    """인터뷰 대화 한 턴"""
    role: str = Field(..., description="ai | user")
    content: str
    turn: int


class UserFlowSessionResponse(BaseModel):
    """인터뷰 세션 응답 (유저 플로우 + 세션 상태)"""
    model_config = ConfigDict(from_attributes=True)

    flow_id: int
    project_id: int
    session_status: str
    current_turn: int
    max_turns: int = 4
    ai_message: str = Field(..., description="AI의 현재 메시지 (질문 또는 최종 결과)")
    interview_history: List[InterviewMessage] = []
    user_flow: Optional[UserFlowResponse] = Field(
        None,
        description="세션 완료 시 최종 유저 플로우 (completed 상태에서만 반환)",
    )


class UserFlowAnswerRequest(BaseModel):
    """기획자 답변 요청"""
    answer: str = Field(..., min_length=1, description="기획자의 답변 텍스트")
    confirm: bool = Field(
        False,
        description="True면 현재 상태로 유저 플로우 생성 확정 (조기 종료)",
    )
