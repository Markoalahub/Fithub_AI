"""
UserFlow Service — CRUD + AI 유저 플로우/와이어프레임/파이프라인 생성

Stage 1: PRD → AI 유저 플로우(DAG) 생성 + DB 저장
Stage 2: 유저 플로우 노드별 ASCII 와이어프레임 생성 + DB 저장
Stage 3: 유저 플로우 + 와이어프레임 → 개발 태스크 분해 + DB 저장
"""
import logging
import tempfile
import os
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from app.models.db.userflow import UserFlow, UserFlowNode, UserFlowEdge
from app.models.db.pipeline import Pipeline, PipelineStep
from app.schemas.userflow import (
    UserFlowNodeCreate,
    UserFlowNodeUpdate,
    UserFlowEdgeCreate,
)
from app.schemas.pipeline import PipelineStepCreate
from app.services import pipeline_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# UserFlow Query
# ──────────────────────────────────────────────

async def get_user_flow(db: AsyncSession, flow_id: int) -> UserFlow:
    """유저 플로우 전체 조회 (nodes + edges 포함)"""
    result = await db.execute(
        select(UserFlow)
        .options(
            selectinload(UserFlow.nodes),
            selectinload(UserFlow.edges),
        )
        .where(UserFlow.id == flow_id)
    )
    flow = result.scalar_one_or_none()
    if flow is None:
        raise HTTPException(status_code=404, detail="유저 플로우를 찾을 수 없습니다.")
    return flow


async def get_user_flows_by_project(
    db: AsyncSession, project_id: int
) -> List[UserFlow]:
    """프로젝트별 유저 플로우 목록 조회"""
    result = await db.execute(
        select(UserFlow)
        .options(
            selectinload(UserFlow.nodes),
            selectinload(UserFlow.edges),
        )
        .where(UserFlow.project_id == project_id)
        .order_by(UserFlow.created_at.desc())
    )
    return list(result.scalars().all())


# ──────────────────────────────────────────────
# UserFlow Node CRUD
# ──────────────────────────────────────────────

async def add_node(
    db: AsyncSession, flow_id: int, data: UserFlowNodeCreate
) -> UserFlowNode:
    """유저 플로우에 노드 추가"""
    # 유저 플로우 존재 확인
    await get_user_flow(db, flow_id)

    node = UserFlowNode(
        user_flow_id=flow_id,
        name=data.name,
        description=data.description,
        node_type=data.node_type,
        sequence_order=data.sequence_order,
    )
    db.add(node)
    await db.flush()
    return node


async def update_node(
    db: AsyncSession, node_id: int, data: UserFlowNodeUpdate
) -> UserFlowNode:
    """유저 플로우 노드 수정"""
    result = await db.execute(
        select(UserFlowNode).where(UserFlowNode.id == node_id)
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="유저 플로우 노드를 찾을 수 없습니다.")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(node, key, value)

    await db.flush()
    return node


async def delete_node(db: AsyncSession, node_id: int) -> None:
    """유저 플로우 노드 삭제 (연결 엣지도 cascade 삭제)"""
    result = await db.execute(
        select(UserFlowNode).where(UserFlowNode.id == node_id)
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="유저 플로우 노드를 찾을 수 없습니다.")

    await db.delete(node)
    await db.flush()


# ──────────────────────────────────────────────
# UserFlow Edge CRUD
# ──────────────────────────────────────────────

async def add_edge(
    db: AsyncSession, flow_id: int, data: UserFlowEdgeCreate
) -> UserFlowEdge:
    """유저 플로우에 엣지(연결) 추가"""
    # 유저 플로우 존재 확인
    await get_user_flow(db, flow_id)

    # 노드 존재 확인
    from_result = await db.execute(
        select(UserFlowNode).where(
            UserFlowNode.id == data.from_node_id,
            UserFlowNode.user_flow_id == flow_id,
        )
    )
    if from_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"출발 노드(ID:{data.from_node_id})를 찾을 수 없습니다.")

    to_result = await db.execute(
        select(UserFlowNode).where(
            UserFlowNode.id == data.to_node_id,
            UserFlowNode.user_flow_id == flow_id,
        )
    )
    if to_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"도착 노드(ID:{data.to_node_id})를 찾을 수 없습니다.")

    edge = UserFlowEdge(
        user_flow_id=flow_id,
        from_node_id=data.from_node_id,
        to_node_id=data.to_node_id,
        label=data.label,
    )
    db.add(edge)
    await db.flush()
    return edge


async def delete_edge(db: AsyncSession, edge_id: int) -> None:
    """유저 플로우 엣지 삭제"""
    result = await db.execute(
        select(UserFlowEdge).where(UserFlowEdge.id == edge_id)
    )
    edge = result.scalar_one_or_none()
    if edge is None:
        raise HTTPException(status_code=404, detail="유저 플로우 엣지를 찾을 수 없습니다.")

    await db.delete(edge)
    await db.flush()


# ──────────────────────────────────────────────
# Stage 1: 인터뷰 세션 기반 유저 플로우 생성
# ──────────────────────────────────────────────

def _parse_pdf_sync(pdf_bytes: bytes) -> str:
    """PDF → 텍스트 변환 (동기)"""
    try:
        from docling.document_converter import DocumentConverter

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        pdf_content = result.document.export_to_markdown()
        os.unlink(tmp_path)
        logger.info(f"[PDF] 파싱 성공: {len(pdf_content)} 자")
        return pdf_content
    except Exception as e:
        logger.error(f"[PDF] 파싱 실패: {e}")
        return ""


async def start_userflow_session(
    db: AsyncSession,
    project_id: int,
    prd_text: str,
    pdf_bytes: Optional[bytes] = None,
) -> dict:
    """
    인터뷰 세션 시작: PRD 분석 → 분석 결과 + 첫 번째 질문 반환

    질문 리스트를 interview_history 메타데이터에 저장하고,
    매 턴마다 하나씩 꺼내서 질문합니다.
    """
    from app.graph.userflow_graph import analyze_prd_for_interview

    # PDF 파싱
    pdf_content = ""
    if pdf_bytes:
        pdf_content = _parse_pdf_sync(pdf_bytes)

    combined_prd = prd_text
    if pdf_content:
        combined_prd += f"\n\n---\n[PDF 원문]\n{pdf_content}"

    # AI 분석 (구조화된 JSON 반환)
    ai_result = await analyze_prd_for_interview(combined_prd)
    analysis = ai_result.get("analysis", "")
    questions = ai_result.get("questions", [])
    features = ai_result.get("features", [])

    # 첫 번째 질문 준비
    first_question = questions[0] if questions else None
    remaining_questions = questions[1:] if len(questions) > 1 else []

    # 첫 AI 메시지: 기능 분석 결과 + 첫 질문
    if first_question:
        ai_message = f"{analysis}\n\n---\n\n🗣️ **인터뷰 시작 (1/{len(questions)})**: {first_question}"
    else:
        ai_message = f"{analysis}\n\n✅ 모든 기능의 범위가 명확합니다. '확정' 버튼을 눌러 유저 플로우를 생성하세요."

    # 인터뷰 이력 초기화
    interview_history = [
        {"role": "ai", "content": ai_message, "turn": 1},
        # 메타데이터: 남은 질문 큐 및 추출된 기능 목록
        {"role": "_meta", "content": "", "turn": 0,
         "pending_questions": remaining_questions,
         "total_questions": len(questions),
         "answered_questions": [],
         "features": features},
    ]

    # DB 저장
    user_flow = UserFlow(
        project_id=project_id,
        title="기능 정의 및 인터뷰 진행 중",
        prd_context=combined_prd,
        interview_history=interview_history,
        session_status="interviewing",
        current_turn=1,
    )
    db.add(user_flow)
    await db.flush()

    logger.info(f"[Session] 세션 시작: flow_id={user_flow.id}, 질문 {len(questions)}개")

    return {
        "flow_id": user_flow.id,
        "project_id": project_id,
        "session_status": "interviewing" if first_question else "ready_to_confirm",
        "current_turn": 1,
        "max_turns": len(questions) + 1,
        "ai_message": ai_message,
        "interview_history": [h for h in interview_history if h.get("role") != "_meta"],
        "user_flow": None,
    }


def _get_meta(history: list) -> dict:
    """interview_history에서 메타데이터 항목을 추출"""
    for h in history:
        if h.get("role") == "_meta":
            return h
    return {"pending_questions": [], "total_questions": 0, "answered_questions": []}


def _set_meta(history: list, meta: dict) -> list:
    """interview_history에서 메타데이터 항목을 갱신"""
    new_history = [h for h in history if h.get("role") != "_meta"]
    new_history.append({
        "role": "_meta", "content": "", "turn": 0,
        "pending_questions": meta.get("pending_questions", []),
        "total_questions": meta.get("total_questions", 0),
        "answered_questions": meta.get("answered_questions", []),
    })
    return new_history


async def handle_session_answer(
    db: AsyncSession,
    flow_id: int,
    user_answer: str,
    force_confirm: bool = False,
) -> dict:
    """
    기획자 답변 처리: 다음 질문 전달 or 최종 유저 플로우 생성

    로직:
      1. 답변을 기록
      2. 남은 질문이 있고 confirm이 아니면 → 다음 질문 반환
      3. 남은 질문이 없거나 confirm이면 → _finalize_user_flow 호출
    """
    from app.graph.userflow_graph import _finalize_user_flow
    from app.schemas.userflow import UserFlowResponse

    user_flow = await get_user_flow(db, flow_id)

    if user_flow.session_status == "completed":
        raise HTTPException(status_code=400, detail="이미 완료된 세션입니다.")

    history = user_flow.interview_history or []
    meta = _get_meta(history)
    current_turn = (user_flow.current_turn or 1) + 1

    pending = meta.get("pending_questions", [])
    total_q = meta.get("total_questions", 0)
    answered = meta.get("answered_questions", [])

    # 사용자 답변 기록
    history.append({"role": "user", "content": user_answer, "turn": current_turn})
    answered.append(user_answer)

    # ── finalize 조건: confirm=True 또는 질문이 모두 소진됨 ──
    if force_confirm or len(pending) == 0:
        result = await _finalize_user_flow(
            prd_text=user_flow.prd_context or "",
            interview_history=[h for h in history if h.get("role") != "_meta"],
            final_answer=user_answer,
        )

        history.append({"role": "ai", "content": result["message"], "turn": current_turn})
        meta["pending_questions"] = []
        meta["answered_questions"] = answered
        history = _set_meta(history, meta)

        # 유저 플로우 DAG 저장
        flow_data = result["user_flow"]
        logger.info(f"[DEBUG] Final flow data from AI: {flow_data}")
        
        if not flow_data.get("nodes"):
            logger.warning("[DEBUG] No nodes found in AI response flow_data")
            
        user_flow.title = flow_data.get("title", "서비스 유저 플로우")
        user_flow.interview_history = history
        user_flow.session_status = "completed"
        user_flow.current_turn = current_turn

        node_name_to_id = {}
        for idx, nd in enumerate(flow_data.get("nodes", [])):
            node = UserFlowNode(
                user_flow_id=flow_id,
                name=nd.get("name", f"기능 {idx+1}"),
                description=nd.get("description", ""),
                node_type=nd.get("node_type", "screen"),
                sequence_order=idx,
            )
            db.add(node)
            await db.flush()
            node_name_to_id[node.name] = node.id

        for ed in flow_data.get("edges", []):
            f_id = node_name_to_id.get(ed.get("from", ""))
            t_id = node_name_to_id.get(ed.get("to", ""))
            if f_id and t_id:
                db.add(UserFlowEdge(
                    user_flow_id=flow_id,
                    from_node_id=f_id, to_node_id=t_id,
                    label=ed.get("label", ""),
                ))

        await db.flush()
        final_flow = await get_user_flow(db, flow_id)
        # 헬퍼 함수를 통한 안전한 직렬화
        flow_response = _serialize_flow(final_flow)

        return {
            "flow_id": flow_id,
            "project_id": user_flow.project_id,
            "session_status": "completed",
            "current_turn": current_turn,
            "max_turns": total_q + 1,
            "ai_message": result["message"],
            "interview_history": [h for h in history if h.get("role") != "_meta"],
            "user_flow": flow_response,
        }

    # ── 다음 질문 전달 ──
    next_question = pending.pop(0)
    q_index = total_q - len(pending)
    ai_message = f"🗣️ **인터뷰 진행 ({q_index}/{total_q})**: {next_question}"

    history.append({"role": "ai", "content": ai_message, "turn": current_turn})
    meta["pending_questions"] = pending
    meta["answered_questions"] = answered
    history = _set_meta(history, meta)

    user_flow.interview_history = history
    user_flow.current_turn = current_turn
    await db.flush()

    return {
        "flow_id": flow_id,
        "project_id": user_flow.project_id,
        "session_status": "interviewing",
        "current_turn": current_turn,
        "max_turns": total_q + 1,
        "ai_message": ai_message,
        "interview_history": [h for h in history if h.get("role") != "_meta"],
        "user_flow": None,
    }


def _serialize_flow(flow: UserFlow) -> dict:
    """SQLAlchemy 모델을 안전하게 JSON 직렬화 가능한 dict로 변환"""
    try:
        from app.schemas.userflow import UserFlowResponse
        # 관계형 데이터(nodes, edges)가 로드되어 있는지 확인 필요 (이미 get_user_flow에서 처리됨)
        return UserFlowResponse.model_validate(flow).model_dump()
    except Exception as e:
        logger.error(f"Serialization failed: {e}")
        # 최소한의 데이터라도 반환
        return {
            "id": flow.id,
            "title": flow.title,
            "nodes": [],
            "edges": []
        }


async def generate_and_save_userflow(
    db: AsyncSession,
    project_id: int,
    prd_text: str,
    pdf_bytes: Optional[bytes] = None,
) -> UserFlow:
    """레거시 원샷 모드: 인터뷰 없이 바로 유저 플로우 생성 (하위 호환)"""
    from app.graph.userflow_graph import generate_user_flow

    pdf_content = ""
    if pdf_bytes:
        pdf_content = _parse_pdf_sync(pdf_bytes)

    flow_data = await generate_user_flow(prd_text, pdf_content)

    user_flow = UserFlow(
        project_id=project_id,
        title=flow_data.get("title", "서비스 유저 플로우"),
        prd_context=prd_text,
        session_status="completed",
        current_turn=0,
    )
    db.add(user_flow)
    await db.flush()

    node_name_to_id = {}
    for idx, node_data in enumerate(flow_data.get("nodes", [])):
        node = UserFlowNode(
            user_flow_id=user_flow.id,
            name=node_data.get("name", f"기능 {idx + 1}"),
            description=node_data.get("description", ""),
            node_type=node_data.get("node_type", "screen"),
            sequence_order=idx,
        )
        db.add(node)
        await db.flush()
        node_name_to_id[node.name] = node.id

    for edge_data in flow_data.get("edges", []):
        from_name = edge_data.get("from", "")
        to_name = edge_data.get("to", "")
        from_id = node_name_to_id.get(from_name)
        to_id = node_name_to_id.get(to_name)

        if from_id and to_id:
            edge = UserFlowEdge(
                user_flow_id=user_flow.id,
                from_node_id=from_id,
                to_node_id=to_id,
                label=edge_data.get("label", ""),
            )
            db.add(edge)

    await db.flush()
    return await get_user_flow(db, user_flow.id)


# ──────────────────────────────────────────────
# Stage 2: AI 와이어프레임 생성 + DB 저장
# ──────────────────────────────────────────────

async def generate_and_save_wireframes(
    db: AsyncSession,
    flow_id: int,
) -> UserFlow:
    """유저 플로우 노드별 ASCII 와이어프레임 생성 + DB 저장"""
    from app.graph.userflow_graph import generate_wireframes

    # 유저 플로우 조회
    user_flow = await get_user_flow(db, flow_id)

    # 노드/엣지 데이터 준비
    nodes_data = [
        {
            "name": node.name,
            "description": node.description or "",
            "node_type": node.node_type,
        }
        for node in user_flow.nodes
    ]
    edges_data = [
        {
            "from_node": edge.from_node.name if edge.from_node else "",
            "to_node": edge.to_node.name if edge.to_node else "",
            "label": edge.label or "",
        }
        for edge in user_flow.edges
    ]

    # AI 와이어프레임 생성
    wireframes = await generate_wireframes(nodes_data, edges_data)

    # DB 업데이트: 각 노드의 wireframe_ascii 필드
    node_name_map = {node.name: node for node in user_flow.nodes}
    for wf in wireframes:
        node_name = wf.get("node_name", "")
        ascii_content = wf.get("ascii", "")
        node = node_name_map.get(node_name)
        if node and ascii_content:
            node.wireframe_ascii = ascii_content
            logger.info(f"[Stage 2] 와이어프레임 저장: {node_name}")
        else:
            logger.warning(f"[Stage 2] 와이어프레임 매칭 실패: {node_name}")

    await db.flush()

    # 갱신된 결과 반환
    return await get_user_flow(db, flow_id)


# ──────────────────────────────────────────────
# Stage 3: 유저 플로우 + 와이어프레임 → 파이프라인 생성
# ──────────────────────────────────────────────

async def generate_and_save_pipeline_from_flow(
    db: AsyncSession,
    flow_id: int,
    project_id: int,
    category: Optional[str] = None,
    tech_stack: Optional[str] = None,
) -> Pipeline:
    """유저 플로우 + 와이어프레임 기반 개발 태스크 분해 → PipelineStep 저장"""
    from app.graph.userflow_graph import generate_pipeline_from_flow

    # 유저 플로우 조회
    user_flow = await get_user_flow(db, flow_id)

    # 노드 데이터 (와이어프레임 포함)
    nodes_data = [
        {
            "name": node.name,
            "description": node.description or "",
            "node_type": node.node_type,
            "wireframe_ascii": node.wireframe_ascii or "",
        }
        for node in user_flow.nodes
    ]
    edges_data = [
        {
            "from_node": edge.from_node.name if edge.from_node else "",
            "to_node": edge.to_node.name if edge.to_node else "",
            "label": edge.label or "",
        }
        for edge in user_flow.edges
    ]

    # AI 태스크 분해
    pipeline_items = await generate_pipeline_from_flow(
        nodes=nodes_data,
        edges=edges_data,
        category=category or "BE",
        tech_stack=tech_stack or "최적 스택",
    )

    # source_node_name → node_id 매핑
    node_name_to_id = {node.name: node.id for node in user_flow.nodes}

    # pipeline_items에 user_flow_node_id 추가
    for item in pipeline_items:
        source_name = item.get("source_node_name", "")
        item["user_flow_node_id"] = node_name_to_id.get(source_name)

    # 기존 save_ai_pipeline_to_db 활용 + user_flow_node_id 확장
    pipeline = await _save_pipeline_with_flow_ref(
        db=db,
        project_id=project_id,
        pipeline_items=pipeline_items,
        category=category,
        tech_stack=tech_stack,
    )

    return pipeline


async def _save_pipeline_with_flow_ref(
    db: AsyncSession,
    project_id: int,
    pipeline_items: list,
    category: Optional[str] = None,
    tech_stack: Optional[str] = None,
) -> Pipeline:
    """PipelineStep에 user_flow_node_id를 포함하여 저장"""
    from app.schemas.pipeline import PipelineCreate, PipelineStepCreate

    # 기존 active 파이프라인 비활성화
    existing = await db.execute(
        select(Pipeline).where(
            Pipeline.project_id == project_id,
            Pipeline.is_active == "Active",
        )
    )
    for pipeline in existing.scalars().all():
        pipeline.is_active = "Inactive"

    # 최신 버전 번호 조회
    version_result = await db.execute(
        select(Pipeline.version)
        .where(Pipeline.project_id == project_id)
        .order_by(Pipeline.version.desc())
        .limit(1)
    )
    latest_version = version_result.scalar_one_or_none() or 0

    # 새 파이프라인 생성
    pipeline = Pipeline(
        project_id=project_id,
        category=category,
        version=latest_version + 1,
        is_active="Active",
        tech_stack=tech_stack,
    )
    db.add(pipeline)
    await db.flush()

    # PipelineStep 생성 (user_flow_node_id 포함)
    for idx, item in enumerate(pipeline_items):
        raw_details = item.get("details", [])
        if isinstance(raw_details, str):
            raw_details = [raw_details]

        raw_tech = item.get("tech_stack", [])
        if isinstance(raw_tech, str):
            raw_tech = [raw_tech]

        step = PipelineStep(
            pipeline_id=pipeline.id,
            step_task_description=item.get("title", ""),
            step_details=raw_details,
            category=item.get("category", category),
            step_sequence_number=idx + 1,
            priority=max(1, min(2, item.get("priority", 1))),
            tech_stack=raw_tech,
            depends_on=item.get("depends_on", []),
            origin="ai_generated_from_flow",
            user_flow_node_id=item.get("user_flow_node_id"),
        )
        db.add(step)

    await db.flush()

    # selectinload로 steps 함께 반환
    result = await db.execute(
        select(Pipeline)
        .options(selectinload(Pipeline.steps))
        .where(Pipeline.id == pipeline.id)
    )
    return result.scalar_one()
