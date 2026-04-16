"""
ORM 모델: Pipeline, PipelineStep

DBML 대응:
  - pipelines: 프로젝트별 파이프라인 (project_id = Logical FK → Spring DB)
  - pipeline_steps: 파이프라인 하위 스텝 (기획자-개발자 승인 포함)
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
    is_active = Column(String(10), nullable=False, default="Active", comment="Active | Inactive")

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
    # 작업 상세 정보
    step_task_description = Column(Text, nullable=False, comment="해당 스텝에서 수행할 구체적인 작업 상세 내용")
    step_sequence_number = Column(Integer, nullable=False, comment="파이프라인 내 작업 배치 순서")

    # GitHub 상태
    step_github_status = Column(
        String(50),
        nullable=False,
        default="Open",
        comment="연동된 깃허브 이슈의 상태: Open | Closed",
    )

    # 승인 정보 (필수)
    step_planner_confirm_yn = Column(
        String(10),
        nullable=False,
        default="Pending",
        comment="기획자의 해당 스텝 승인 여부: Pending | Approved",
    )
    step_developer_confirm_yn = Column(
        String(10),
        nullable=False,
        default="Pending",
        comment="개발자의 해당 스텝 승인 여부: Pending | Approved",
    )
    step_confirmation_date = Column(
        DateTime,
        nullable=True,
        comment="양측 승인이 완료되어 스텝이 확정된 날짜",
    )

    # 추가 정보
    duration = Column(String(100), nullable=True, comment="예상 소요 시간 (예: '2-3일')")
    tech_stack = Column(String(200), nullable=True, comment="기술스택 (예: 'Spring Boot 3.x')")
    origin = Column(
        String(50),
        nullable=True,
        comment="생성 출처: ai_generated | user_created | meeting_derived",
    )

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    pipeline = relationship("Pipeline", back_populates="steps")
    meeting_relations = relationship(
        "MeetingStepRelation",
        back_populates="pipeline_step",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<PipelineStep(id={self.id}, seq={self.step_sequence_number}, status={self.step_final_confirmed_status})>"

    @property
    def step_final_confirmed_status(self) -> str:
        """계산 필드: 기획자와 개발자 모두 승인되었는지 확인"""
        if (
            self.step_planner_confirm_yn == "Approved"
            and self.step_developer_confirm_yn == "Approved"
        ):
            return "Confirmed"
        return "Pending"
