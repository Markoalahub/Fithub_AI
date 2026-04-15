"""
ORM 모델: MeetingLog, MeetingAttendee, MeetingStepRelation

DBML 대응:
  - meeting_logs: 회의록 (project_id = Logical FK → Spring DB)
  - meeting_attendees: 회의 참석자 매핑 (user_id = Logical FK → Spring DB)
  - meeting_step_relations: 회의록 ↔ 파이프라인 스텝 관계
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
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
