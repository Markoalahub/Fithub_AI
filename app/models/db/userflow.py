"""
ORM 모델: UserFlow, UserFlowNode, UserFlowEdge

DBML 대응:
  - user_flows: 프로젝트별 서비스 유저 플로우 (DAG 루트)
  - user_flow_nodes: 유저 플로우 내 기능 노드 (화면/기능 단위)
  - user_flow_edges: 노드 간 연결 (DAG 엣지)
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class UserFlow(Base):
    """프로젝트별 서비스 유저 플로우 (DAG 루트)"""
    __tablename__ = "user_flows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Logical FK -> Spring DB: projects.id",
    )
    title = Column(String(200), nullable=True, comment="유저 플로우 제목")
    prd_context = Column(
        Text,
        nullable=True,
        comment="원본 PRD 텍스트 (Stage 2, 3 참조용)",
    )

    # 인터뷰 세션 필드
    interview_history = Column(
        JSON,
        nullable=True,
        comment='인터뷰 대화 이력 [{"role": "ai"|"user", "content": "...", "turn": 1}]',
    )
    session_status = Column(
        String(50),
        nullable=False,
        default="interviewing",
        comment="세션 상태: interviewing | confirmed | completed",
    )
    current_turn = Column(
        Integer,
        nullable=False,
        default=1,
        comment="현재 인터뷰 턴 번호 (최대 4)",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    # Relationships
    nodes = relationship(
        "UserFlowNode",
        back_populates="user_flow",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UserFlowNode.sequence_order.asc()",
    )
    edges = relationship(
        "UserFlowEdge",
        back_populates="user_flow",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<UserFlow(id={self.id}, project_id={self.project_id}, title={self.title})>"


class UserFlowNode(Base):
    """유저 플로우 내 기능 노드 (하나의 화면/기능 단위)"""
    __tablename__ = "user_flow_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_flow_id = Column(
        Integer,
        ForeignKey("user_flows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(
        String(200),
        nullable=False,
        comment="기능명 (로그인, 홈 화면 등)",
    )
    description = Column(Text, nullable=True, comment="기능 상세 설명")
    node_type = Column(
        String(50),
        nullable=False,
        default="screen",
        comment="screen | process | decision",
    )
    wireframe_ascii = Column(
        Text,
        nullable=True,
        comment="Stage 2에서 생성되는 ASCII 와이어프레임",
    )
    sequence_order = Column(
        Integer,
        nullable=False,
        default=0,
        comment="표시 순서",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    # Relationships
    user_flow = relationship("UserFlow", back_populates="nodes")
    pipeline_steps = relationship(
        "PipelineStep",
        back_populates="user_flow_node",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<UserFlowNode(id={self.id}, name={self.name}, type={self.node_type})>"


class UserFlowEdge(Base):
    """유저 플로우 노드 간 연결 (DAG 엣지)"""
    __tablename__ = "user_flow_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_flow_id = Column(
        Integer,
        ForeignKey("user_flows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_node_id = Column(
        Integer,
        ForeignKey("user_flow_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_node_id = Column(
        Integer,
        ForeignKey("user_flow_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(
        String(200),
        nullable=True,
        comment="연결 조건/설명 (예: '인증 성공 시')",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    # Relationships
    user_flow = relationship("UserFlow", back_populates="edges")
    from_node = relationship(
        "UserFlowNode",
        foreign_keys=[from_node_id],
        lazy="selectin",
    )
    to_node = relationship(
        "UserFlowNode",
        foreign_keys=[to_node_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<UserFlowEdge(id={self.id}, {self.from_node_id} -> {self.to_node_id})>"
