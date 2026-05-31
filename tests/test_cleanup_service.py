import unittest

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.db.meeting import MeetingAttendee, MeetingLog, MeetingStepRelation
from app.models.db.pipeline import Pipeline, PipelineStep
from app.services.cleanup_service import cleanup_project_resources


class CleanupServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_cleanup_project_resources_deletes_project_owned_rows(self):
        async with self.session_factory() as session:
            pipeline = Pipeline(project_id=1, category="BE", version=1)
            other_pipeline = Pipeline(project_id=2, category="BE", version=1)
            session.add_all([pipeline, other_pipeline])
            await session.flush()

            step = PipelineStep(
                pipeline_id=pipeline.id,
                step_task_description="target step",
                category="BE",
                step_sequence_number=1,
                priority=1,
            )
            other_step = PipelineStep(
                pipeline_id=other_pipeline.id,
                step_task_description="other step",
                category="BE",
                step_sequence_number=1,
                priority=1,
            )
            session.add_all([step, other_step])
            await session.flush()

            meeting = MeetingLog(project_id=1, content="target meeting")
            other_meeting = MeetingLog(project_id=2, content="other meeting")
            session.add_all([meeting, other_meeting])
            await session.flush()

            session.add_all([
                MeetingAttendee(meeting_log_id=meeting.id, user_id=1),
                MeetingAttendee(meeting_log_id=other_meeting.id, user_id=2),
                MeetingStepRelation(meeting_log_id=meeting.id, pipeline_step_id=step.id),
                MeetingStepRelation(meeting_log_id=other_meeting.id, pipeline_step_id=other_step.id),
            ])
            await session.flush()

            deleted = await cleanup_project_resources(session, project_id=1)

            self.assertEqual(deleted["meeting_step_relations"], 1)
            self.assertEqual(deleted["meeting_attendees"], 1)
            self.assertEqual(deleted["meeting_logs"], 1)
            self.assertEqual(deleted["pipeline_steps"], 1)
            self.assertEqual(deleted["pipelines"], 1)

            self.assertEqual(await self._count(session, MeetingStepRelation), 1)
            self.assertEqual(await self._count(session, MeetingAttendee), 1)
            self.assertEqual(await self._count(session, MeetingLog), 1)
            self.assertEqual(await self._count(session, PipelineStep), 1)
            self.assertEqual(await self._count(session, Pipeline), 1)

    async def test_cleanup_project_resources_is_idempotent(self):
        async with self.session_factory() as session:
            first = await cleanup_project_resources(session, project_id=999)
            second = await cleanup_project_resources(session, project_id=999)

            self.assertTrue(all(count == 0 for count in first.values()))
            self.assertTrue(all(count == 0 for count in second.values()))

    async def _count(self, session, model) -> int:
        return await session.scalar(select(func.count()).select_from(model))
