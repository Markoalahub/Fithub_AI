"""Internal cleanup operations used by the Spring outbox worker."""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.meeting import MeetingAttendee, MeetingLog, MeetingStepRelation
from app.models.db.pipeline import Pipeline, PipelineStep


async def cleanup_project_resources(db: AsyncSession, project_id: int) -> dict:
    """Delete all AI-owned rows for a Spring project id.

    The endpoint using this service is idempotent: deleting an already-cleaned
    project returns successfully with zero counts.
    """
    deleted = {
        "meeting_step_relations": 0,
        "meeting_attendees": 0,
        "meeting_logs": 0,
        "pipeline_steps": 0,
        "pipelines": 0,
    }

    meeting_ids = list((await db.execute(
        select(MeetingLog.id).where(MeetingLog.project_id == project_id)
    )).scalars().all())
    if meeting_ids:
        result = await db.execute(delete(MeetingStepRelation).where(
            MeetingStepRelation.meeting_log_id.in_(meeting_ids)
        ))
        deleted["meeting_step_relations"] += result.rowcount or 0

        result = await db.execute(delete(MeetingAttendee).where(
            MeetingAttendee.meeting_log_id.in_(meeting_ids)
        ))
        deleted["meeting_attendees"] += result.rowcount or 0

        result = await db.execute(delete(MeetingLog).where(MeetingLog.id.in_(meeting_ids)))
        deleted["meeting_logs"] += result.rowcount or 0

    pipeline_ids = list((await db.execute(
        select(Pipeline.id).where(Pipeline.project_id == project_id)
    )).scalars().all())
    if pipeline_ids:
        step_ids = list((await db.execute(
            select(PipelineStep.id).where(PipelineStep.pipeline_id.in_(pipeline_ids))
        )).scalars().all())
        if step_ids:
            result = await db.execute(delete(MeetingStepRelation).where(
                MeetingStepRelation.pipeline_step_id.in_(step_ids)
            ))
            deleted["meeting_step_relations"] += result.rowcount or 0

        result = await db.execute(delete(PipelineStep).where(
            PipelineStep.pipeline_id.in_(pipeline_ids)
        ))
        deleted["pipeline_steps"] += result.rowcount or 0

        result = await db.execute(delete(Pipeline).where(Pipeline.id.in_(pipeline_ids)))
        deleted["pipelines"] += result.rowcount or 0

    await db.flush()
    return deleted
