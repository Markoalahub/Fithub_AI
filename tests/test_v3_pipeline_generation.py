import unittest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.db.pipeline import Pipeline
from app.routers.pipeline_router import _generate_and_save_v3_pipeline_for_category


class FakePipelineGraph:
    def __init__(self):
        self.categories = []

    async def ainvoke(self, state, config):
        category = state["category"]
        self.categories.append(category)
        return {
            "final_pipeline": [
                {
                    "title": f"{category} 작업 생성",
                    "details": [f"{category} 상세 작업"],
                    "category": category,
                    "priority": 1,
                    "tech_stack": [],
                }
            ]
        }


class V3PipelineGenerationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_all_generation_path_creates_separate_be_and_fe_pipelines(self):
        async with self.session_factory() as session:
            graph = FakePipelineGraph()

            be_response = await _generate_and_save_v3_pipeline_for_category(
                db=session,
                graph=graph,
                project_id=1,
                requirements="requirements",
                category="BE",
                tech_stack="Spring Boot",
                pdf_bytes=None,
            )
            fe_response = await _generate_and_save_v3_pipeline_for_category(
                db=session,
                graph=graph,
                project_id=1,
                requirements="requirements",
                category="FE",
                tech_stack="React",
                pdf_bytes=None,
            )

            pipelines = list((await session.execute(
                select(Pipeline).where(Pipeline.project_id == 1).order_by(Pipeline.category.asc())
            )).scalars().all())

            self.assertEqual(graph.categories, ["BE", "FE"])
            self.assertEqual([pipeline.category for pipeline in pipelines], ["BE", "FE"])
            self.assertEqual([pipeline.version for pipeline in pipelines], [1, 1])
            self.assertEqual([pipeline.is_active for pipeline in pipelines], ["Active", "Active"])
            self.assertEqual(be_response.category, "BE")
            self.assertEqual(fe_response.category, "FE")

    async def test_save_ai_pipeline_versions_and_deactivates_by_category_only(self):
        async with self.session_factory() as session:
            graph = FakePipelineGraph()

            old_be = await _generate_and_save_v3_pipeline_for_category(
                db=session,
                graph=graph,
                project_id=1,
                requirements="requirements",
                category="BE",
                tech_stack="Spring Boot",
                pdf_bytes=None,
            )
            fe = await _generate_and_save_v3_pipeline_for_category(
                db=session,
                graph=graph,
                project_id=1,
                requirements="requirements",
                category="FE",
                tech_stack="React",
                pdf_bytes=None,
            )
            new_be = await _generate_and_save_v3_pipeline_for_category(
                db=session,
                graph=graph,
                project_id=1,
                requirements="requirements",
                category="BE",
                tech_stack="Spring Boot",
                pdf_bytes=None,
            )

            pipelines = list((await session.execute(
                select(Pipeline).where(Pipeline.project_id == 1).order_by(Pipeline.id.asc())
            )).scalars().all())

            self.assertEqual(old_be.version, 1)
            self.assertEqual(fe.version, 1)
            self.assertEqual(new_be.version, 2)
            self.assertEqual(
                [(pipeline.category, pipeline.version, pipeline.is_active) for pipeline in pipelines],
                [
                    ("BE", 1, "Inactive"),
                    ("FE", 1, "Active"),
                    ("BE", 2, "Active"),
                ],
            )
