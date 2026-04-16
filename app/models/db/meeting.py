"""
ORM 모델: MeetingLog, MeetingAttendee, MeetingStepRelation

DBML 대응:
  - meeting_logs: 회의록 (project_id = Logical FK → Spring DB)
  - meeting_attendees: 회의 참석자 매핑 (user_id = Logical FK → Spring DB)
  - meeting_step_relations: 회의록 ↔ 파이프라인 스텝 관계
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class MeetingLog(Base):
    __tablename__ = "meeting_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Logical FK -> Spring DB: projects.id",
    )
    content = Column(Text, nullable=False, comment="원본 회의 내용")
    summary = Column(Text, nullable=True, comment="AI 요약 결과")
    vector_id = Column(
        String(255),
        nullable=True,
        comment="벡터 DB 참조 ID (Pinecone / Chroma 등)",
    )

    # 스텝 조정 관련 필드
    meeting_log_content = Column(
        Text,
        nullable=True,
        comment="(선택 사항) 스텝 조정 시 발생한 회의 기록",
    )
    ai_translated_explanation = Column(
        Text,
        nullable=True,
        comment="기술 소통을 돕기 위해 AI가 변환한 설명 텍스트",
    )

    # 번역 세션 관련 필드
    is_translation_session = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="번역 세션 여부",
    )
    conversation_type = Column(
        String(50),
        nullable=False,
        default="meeting",
        comment="회의 타입: 'meeting' | 'translation'",
    )
    translation_history = Column(
        JSON,
        nullable=True,
        comment="번역 대화 이력 JSON (messages 배열 포함)",
    )
    embedding = Column(
        String,
        nullable=True,
        comment="벡터 임베딩 (JSON 문자열 또는 pgvector)",
    )
    session_status = Column(
        String(50),
        nullable=False,
        default="ongoing",
        comment="세션 상태: 'ongoing' | 'completed'",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    # Relationships
    attendees = relationship(
        "MeetingAttendee",
        back_populates="meeting_log",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    step_relations = relationship(
        "MeetingStepRelation",
        back_populates="meeting_log",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<MeetingLog(id={self.id}, project_id={self.project_id})>"


class MeetingAttendee(Base):
    __tablename__ = "meeting_attendees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_log_id = Column(
        Integer,
        ForeignKey("meeting_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Logical FK -> Spring DB: users.id",
    )

    # Relationships
    meeting_log = relationship("MeetingLog", back_populates="attendees")

    def __repr__(self) -> str:
        return f"<MeetingAttendee(id={self.id}, user_id={self.user_id})>"


class MeetingStepRelation(Base):
    __tablename__ = "meeting_step_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_log_id = Column(
        Integer,
        ForeignKey("meeting_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_step_id = Column(
        Integer,
        ForeignKey("pipeline_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    meeting_log = relationship("MeetingLog", back_populates="step_relations")
    pipeline_step = relationship(
        "PipelineStep", back_populates="meeting_relations"
    )

    def __repr__(self) -> str:
        return (
            f"<MeetingStepRelation(meeting={self.meeting_log_id}, "
            f"step={self.pipeline_step_id})>"
        )
