"""Internal APIs for service-to-service maintenance calls."""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.cleanup_service import cleanup_project_resources

router = APIRouter(prefix="/internal", tags=["Internal"])


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="프로젝트 관련 AI 데이터 삭제",
    include_in_schema=False,
)
async def delete_project_resources(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    await cleanup_project_resources(db, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
