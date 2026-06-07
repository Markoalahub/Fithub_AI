import unittest

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.main import app
from app.models.db.pipeline import Pipeline
from app.routers.pipeline_router import update_pipeline_github_repository
from app.schemas.pipeline import (
    PipelineGithubRepositoryUpdate,
    PipelineResponse,
    PipelineV3Response,
)
from app.services import pipeline_service


class PipelineGithubRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_update_pipeline_github_repository_url_links_repo_one_to_one(self):
        async with self.session_factory() as session:
            pipeline = Pipeline(project_id=1, category="BE", version=1)
            session.add(pipeline)
            await session.flush()

            updated = await pipeline_service.update_pipeline_github_repository_url(
                session,
                pipeline.id,
                "https://github.com/Markoalahub/Fithub_BE",
            )

            persisted = (await session.execute(
                select(Pipeline).where(Pipeline.id == pipeline.id)
            )).scalar_one()
            response = PipelineV3Response.model_validate(updated)

            self.assertEqual(updated.github_repo_url, "https://github.com/Markoalahub/Fithub_BE")
            self.assertEqual(persisted.github_repo_url, "https://github.com/Markoalahub/Fithub_BE")
            self.assertEqual(response.github_repo_url, "https://github.com/Markoalahub/Fithub_BE")

    async def test_update_pipeline_github_repository_router_returns_pipeline_response(self):
        async with self.session_factory() as session:
            pipeline = Pipeline(project_id=1, category="FE", version=1)
            session.add(pipeline)
            await session.flush()

            response = await update_pipeline_github_repository(
                pipeline_id=pipeline.id,
                data=PipelineGithubRepositoryUpdate(
                    github_repo_url=" https://github.com/Markoalahub/Fithub_FE "
                ),
                db=session,
            )
            response_model = PipelineResponse.model_validate(response)

            self.assertEqual(response_model.github_repo_url, "https://github.com/Markoalahub/Fithub_FE")

    async def test_update_pipeline_github_repository_url_raises_404_for_missing_pipeline(self):
        async with self.session_factory() as session:
            with self.assertRaises(HTTPException) as context:
                await pipeline_service.update_pipeline_github_repository_url(
                    session,
                    999,
                    "https://github.com/Markoalahub/missing",
                )

            self.assertEqual(context.exception.status_code, 404)

    async def test_github_repository_route_uses_patch_method(self):
        route_methods = {
            method.lower()
            for route in app.routes
            if getattr(route, "path", None) == "/pipelines/{pipeline_id}/github-repository"
            for method in getattr(route, "methods", set())
        }

        self.assertIn("patch", route_methods)
        self.assertNotIn("put", route_methods)
