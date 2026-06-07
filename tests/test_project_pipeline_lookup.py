import unittest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.db.pipeline import Pipeline, PipelineStep
from app.routers.project_pipeline_router import get_project_pipelines
from app.schemas.pipeline import PipelineSummaryListResponse, PipelineV3Response


class ProjectPipelineLookupTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_project_pipeline_lookup_returns_summaries_without_category(self):
        async with self.session_factory() as session:
            session.add_all([
                Pipeline(project_id=1, category="BE", version=1),
                Pipeline(project_id=1, category="FE", version=2),
                Pipeline(project_id=2, category="AI", version=1),
            ])
            await session.flush()

            response = await get_project_pipelines(project_id=1, category=None, db=session)

            self.assertIsInstance(response, PipelineSummaryListResponse)
            self.assertEqual(response.project_id, 1)
            self.assertEqual(response.total, 2)
            self.assertEqual(
                [summary.pipeline_name for summary in response.pipelines],
                [
                    f"BE 파이프라인 {response.pipelines[0].pipe_id}",
                    f"FE 파이프라인 {response.pipelines[1].pipe_id}",
                ],
            )

    async def test_project_pipeline_lookup_returns_latest_category_pipeline(self):
        async with self.session_factory() as session:
            old_pipeline = Pipeline(project_id=1, category="FE", version=1)
            latest_pipeline = Pipeline(project_id=1, category="FE", version=2, tech_stack="React, expo")
            session.add_all([old_pipeline, latest_pipeline])
            await session.flush()
            session.add(
                PipelineStep(
                    pipeline_id=latest_pipeline.id,
                    step_task_description="[UI 컴포넌트] 사용자 입력 폼 개발",
                    step_details=["[UI] 총 예산 상한가 입력 필드 컴포넌트 개발"],
                    category="FE",
                    step_sequence_number=1,
                    priority=1,
                )
            )
            await session.flush()

            response = await get_project_pipelines(project_id=1, category="fe", db=session)

            self.assertIsInstance(response, PipelineV3Response)
            self.assertEqual(response.pipe_id, latest_pipeline.id)
            self.assertEqual(response.project_id, 1)
            self.assertEqual(response.category, "FE")
            self.assertEqual(response.version, 2)
            self.assertEqual(response.tech_stack, "React, expo")
            self.assertEqual(len(response.feats), 1)
            self.assertEqual(response.feats[0].feat_title, "[UI 컴포넌트] 사용자 입력 폼 개발")

    async def test_project_pipeline_lookup_raises_404_for_missing_category(self):
        async with self.session_factory() as session:
            session.add(Pipeline(project_id=1, category="BE", version=1))
            await session.flush()

            with self.assertRaises(HTTPException) as context:
                await get_project_pipelines(project_id=1, category="AI", db=session)

            self.assertEqual(context.exception.status_code, 404)
