"""
UserFlow Router — REST API

엔드포인트:
  GET    /userflow/{flow_id}              → 유저 플로우 전체 조회
  GET    /userflow/project/{project_id}   → 프로젝트별 유저 플로우 목록

  POST   /userflow/{flow_id}/nodes        → 노드 추가
  PATCH  /userflow/nodes/{node_id}        → 노드 수정
  DELETE /userflow/nodes/{node_id}        → 노드 삭제

  POST   /userflow/{flow_id}/edges        → 엣지 추가
  DELETE /userflow/edges/{edge_id}        → 엣지 삭제
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.userflow import (
    UserFlowResponse,
    UserFlowListResponse,
    UserFlowNodeCreate,
    UserFlowNodeUpdate,
    UserFlowNodeResponse,
    UserFlowEdgeCreate,
    UserFlowEdgeResponse,
)
from app.services import userflow_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/userflow", tags=["UserFlow"])


# ──────────────────────────────────────────────
# UserFlow Query
# ──────────────────────────────────────────────

@router.get(
    "/{flow_id}",
    response_model=UserFlowResponse,
    summary="유저 플로우 전체 조회",
    description="특정 유저 플로우의 모든 노드와 엣지를 포함하여 조회합니다.",
)
async def get_user_flow(
    flow_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await userflow_service.get_user_flow(db, flow_id)


@router.get(
    "/project/{project_id}",
    response_model=UserFlowListResponse,
    summary="프로젝트별 유저 플로우 목록",
    description="특정 프로젝트의 모든 유저 플로우 목록을 조회합니다.",
)
async def get_user_flows_by_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    flows = await userflow_service.get_user_flows_by_project(db, project_id)
    return UserFlowListResponse(user_flows=flows, total=len(flows))


# ──────────────────────────────────────────────
# Node CRUD
# ──────────────────────────────────────────────

@router.post(
    "/{flow_id}/nodes",
    response_model=UserFlowNodeResponse,
    status_code=201,
    summary="유저 플로우 노드 추가",
    description="유저 플로우에 새로운 기능 노드를 추가합니다.",
)
async def add_node(
    flow_id: int,
    data: UserFlowNodeCreate,
    db: AsyncSession = Depends(get_db),
):
    return await userflow_service.add_node(db, flow_id, data)


@router.patch(
    "/nodes/{node_id}",
    response_model=UserFlowNodeResponse,
    summary="유저 플로우 노드 수정",
    description="유저 플로우 노드의 이름, 설명, 타입 등을 수정합니다.",
)
async def update_node(
    node_id: int,
    data: UserFlowNodeUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await userflow_service.update_node(db, node_id, data)


@router.delete(
    "/nodes/{node_id}",
    status_code=204,
    summary="유저 플로우 노드 삭제",
    description="유저 플로우 노드를 삭제합니다. 연결된 엣지도 함께 삭제됩니다.",
)
async def delete_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
):
    await userflow_service.delete_node(db, node_id)


# ──────────────────────────────────────────────
# Edge CRUD
# ──────────────────────────────────────────────

@router.post(
    "/{flow_id}/edges",
    response_model=UserFlowEdgeResponse,
    status_code=201,
    summary="유저 플로우 엣지 추가",
    description="두 노드 간 연결(엣지)을 추가합니다.",
)
async def add_edge(
    flow_id: int,
    data: UserFlowEdgeCreate,
    db: AsyncSession = Depends(get_db),
):
    return await userflow_service.add_edge(db, flow_id, data)


@router.delete(
    "/edges/{edge_id}",
    status_code=204,
    summary="유저 플로우 엣지 삭제",
    description="두 노드 간 연결(엣지)을 삭제합니다.",
)
async def delete_edge(
    edge_id: int,
    db: AsyncSession = Depends(get_db),
):
    await userflow_service.delete_edge(db, edge_id)
