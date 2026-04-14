"""
ORM 모델: Pipeline, PipelineStep

DBML 대응:
  - pipelines: 프로젝트별 파이프라인 (project_id = Logical FK → Spring DB)
  - pipeline_steps: 파이프라인 하위 스텝
"""
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Pipeline(Base):
    __tablename__ = "pipelines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Logical FK -> Spring DB: projects.id",
    )
    category = Column(String(100), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    steps = relationship(
        "PipelineStep",
        back_populates="pipeline",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Pipeline(id={self.id}, project_id={self.project_id}, v{self.version})>"


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_id = Column(
        Integer,
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    duration = Column(String(100), nullable=True, comment="예상 소요 시간 (예: '2-3일')")
    tech_stack = Column(String(200), nullable=True, comment="기술스택 (예: 'Spring Boot 3.x')")
    is_completed = Column(Boolean, nullable=False, default=False)
    origin = Column(
        String(50),
        nullable=True,
        comment="생성 출처: ai_generated | user_created | meeting_derived",
    )

    # Relationships
    pipeline = relationship("Pipeline", back_populates="steps")
    meeting_relations = relationship(
        "MeetingStepRelation",
        back_populates="pipeline_step",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<PipelineStep(id={self.id}, title='{self.title}')>"
