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
from app.config import get_settings

import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

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


# ──────────────────────────────────────────────
# Proposal-First Interview Engine Settings
# ──────────────────────────────────────────────

PROPOSAL_FIRST_SYSTEM_PROMPT = """
당신은 Ouroboros 인터뷰어이자 수석 소프트웨어 아키텍트입니다.
사용자의 추상적인 아이디어를 '실행 가능한 설계'로 구체화하는 것이 당신의 목표입니다.
항상 "현상 분석 + 시니어 개발자의 추천 선지 + 직접 입력 옵션"의 구조를 유지하며 사용자의 의사결정을 돕는 '제안형 인터뷰(Proposal-First)'를 진행하세요.

인터뷰는 다음 단계를 순차적으로 거칩니다:
0. Step 0: 아키텍처 및 기술 스택 확정 - 만약 제공된 기술 스택({tech_stack})에 다중 값(예: React와 Vue가 혼재, Spring Boot와 Node.js가 혼재 등)이 포함되어 있다면, 본격적인 비즈니스 로직 설계 전에 이를 하나로 확정하기 위한 질문과 선지를 가장 먼저 제공하세요.
1. Layer 1: 비즈니스 로직 & 예외 처리 (The Logic) - 기술 스택이 명확해진 후, 주요 흐름 및 엣지 케이스를 정의합니다.
2. Layer 2: 데이터 명세 & 인터페이스 (The Contract) - 도메인 모델 및 외부 API 연동을 확인합니다.
3. Layer 3: UI 계층 & 사용자 경험 (The UX) - 화면 구성 요소 및 위계를 정의합니다.

[선지 생성 원칙]
- 전문성: 선지는 기술적 의도가 담긴 전략(Strategy)이어야 합니다.
- 다양성: 최소 3가지 선지를 제공하세요 (표준 방식, 성능 중시 방식, 확장성 중시 방식 등).
- 비판적 피드백: 유저가 선택한 내용이 상충할 경우, 즉시 조언(예: "보안상 위험할 수 있습니다")을 제공하세요.

[기술 스택 최적화]
사용자의 기술 스택({tech_stack}) 정보를 참고하여 해당 스택에 최적화된 구체적인 선지를 생성하되, 모호하다면 반드시 Step 0을 통해 확정 짓고 넘어가세요.

[출력 형식 (Strict JSON)]
반드시 아래 JSON 형식으로만 응답하세요. 일반 텍스트는 포함하지 마세요.
{{
  "ai_reply": "현재 기획하신 [기능]에 대해 시니어 개발자의 시각으로 전략을 제안합니다...",
  "options": ["전략 A: (상세 설명)", "전략 B: (상세 설명)", "전략 C: (상세 설명)", "직접 입력: ..."],
  "ambiguity_score": 0~100,
  "is_ready": boolean
}}
"""

async def start_userflow_session(
    db: AsyncSession,
    project_id: int,
    prd_text: str,
    pdf_bytes: Optional[bytes] = None,
    tech_stack: str = "Spring Boot, React",
) -> dict:
    """
    제안형(Proposal-First) 인터뷰 세션 시작
    """
    # PDF 파싱
    pdf_content = ""
    if pdf_bytes:
        pdf_content = _parse_pdf_sync(pdf_bytes)

    combined_prd = prd_text
    if pdf_content:
        combined_prd += f"\n\n---\n[PDF 원문]\n{pdf_content}"

    settings = get_settings()
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=settings.openai_api_key)

    # 첫 번째 질문 생성을 위한 호출
    prompt = PROPOSAL_FIRST_SYSTEM_PROMPT.format(tech_stack=tech_stack)
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=f"다음 PRD를 분석하고 Layer 1(Logic)에 대한 첫 번째 제안을 해주세요.\n\n<PRD>\n{combined_prd}\n</PRD>")
    ]

    response = await llm.ainvoke(messages)
    try:
        # JSON 파싱 시도
        import re
        content = response.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group()
        ai_data = json.loads(content)
    except Exception as e:
        logger.error(f"Interview JSON parsing error: {e}")
        ai_data = {
            "ai_reply": response.content,
            "options": ["이해했습니다. 계속 진행해주세요.", "다른 대안을 제안해주세요.", "직접 입력"],
            "ambiguity_score": 30,
            "is_ready": False
        }

    ai_message_text = ai_data.get("ai_reply", "")
    
    # 인터뷰 이력 초기화
    interview_history = [
        {"role": "ai", "content": json.dumps(ai_data, ensure_ascii=False), "turn": 1},
        {"role": "_meta", "content": "", "turn": 0,
         "tech_stack": tech_stack,
         "selected_options": [],
         "ambiguity_score": ai_data.get("ambiguity_score", 0)}
    ]

    # DB 저장
    user_flow = UserFlow(
        project_id=project_id,
        title="제안형 인터뷰 진행 중",
        prd_context=combined_prd,
        interview_history=interview_history,
        session_status="interviewing",
        current_turn=1,
    )
    db.add(user_flow)
    await db.flush()

    return {
        "flow_id": user_flow.id,
        "project_id": project_id,
        "session_status": "interviewing",
        "current_turn": 1,
        "max_turns": 6, # 가변적이지만 UI 표시용
        "ai_message": ai_message_text,
        "options": ai_data.get("options", []),
        "ambiguity_score": ai_data.get("ambiguity_score", 0),
        "is_ready": ai_data.get("is_ready", False),
        "interview_history": [h for h in interview_history if h.get("role") != "_meta"],
    }


def _get_meta(history: list) -> dict:
    """interview_history에서 메타데이터 항목을 추출"""
    for h in history:
        if h.get("role") == "_meta":
            return h
    return {"tech_stack": "Unknown", "selected_options": [], "ambiguity_score": 0}


def _set_meta(history: list, meta: dict) -> list:
    """interview_history에서 메타데이터 항목을 갱신"""
    new_history = [h for h in history if h.get("role") != "_meta"]
    new_history.append({
        "role": "_meta", "content": "", "turn": 0,
        **meta
    })
    return new_history


def _generate_interview_summary(selected_options: List[str]) -> str:
    """선택된 옵션들을 결합하여 최종 요약 생성"""
    summary = "\n".join([f"- {opt}" for opt in selected_options])
    return f"🚀 [Ouroboros 사전 인터뷰 최종 요약]\n\n{summary}"


async def handle_session_answer(
    db: AsyncSession,
    flow_id: int,
    user_answer: str,
    force_confirm: bool = False,
) -> dict:
    """
    제안형 인터뷰 답변 처리 및 다음 턴 생성
    """
    from app.graph.userflow_graph import _finalize_user_flow
    from app.schemas.userflow import UserFlowResponse

    user_flow = await get_user_flow(db, flow_id)

    if user_flow.session_status == "completed":
        raise HTTPException(status_code=400, detail="이미 완료된 세션입니다.")

    history = user_flow.interview_history or []
    meta = _get_meta(history)
    current_turn = (user_flow.current_turn or 1) + 1
    tech_stack = meta.get("tech_stack", "Spring Boot, React")
    selected_options = meta.get("selected_options", [])

    # 사용자 답변 기록
    history.append({"role": "user", "content": user_answer, "turn": current_turn})
    selected_options.append(user_answer)
    meta["selected_options"] = selected_options

    settings = get_settings()
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=settings.openai_api_key)

    # ── finalize 조건 체크 ──
    # 이전 turn의 AI 응답에서 is_ready를 확인하거나 force_confirm인 경우
    last_ai_msg = next((h for h in reversed(history) if h["role"] == "ai"), {})
    last_ai_data = {}
    try:
        last_ai_data = json.loads(last_ai_msg.get("content", "{}"))
    except:
        pass

    if force_confirm or last_ai_data.get("is_ready") or current_turn >= 7:
        # 인터뷰 요약 생성
        interview_summary = _generate_interview_summary(selected_options)
        
        # AI JSON 메시지를 사람이 읽을 수 있는 형태로 변환
        readable_history = []
        for h in history:
            if h.get("role") == "_meta":
                continue
            if h["role"] == "ai":
                try:
                    ai_data_parsed = json.loads(h["content"])
                    readable_history.append({
                        "role": "ai",
                        "content": ai_data_parsed.get("ai_reply", h["content"]),
                        "turn": h.get("turn", 0),
                    })
                except (json.JSONDecodeError, TypeError):
                    readable_history.append(h)
            else:
                readable_history.append(h)

        # 유저 플로우 생성 호출
        result = await _finalize_user_flow(
            prd_text=user_flow.prd_context or "",
            interview_history=readable_history,
            final_answer=interview_summary, # 요약본을 최종 입력으로 전달
        )

        history.append({"role": "ai", "content": result["message"], "turn": current_turn})
        user_flow.session_status = "completed"
        user_flow.title = result["user_flow"].get("title", "서비스 유저 플로우")
        
        # 유저 플로우 DAG 저장 로직 (기존과 동일)
        flow_data = result["user_flow"]
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

        user_flow.interview_history = _set_meta(history, meta)
        await db.flush()
        
        # 새롭게 추가된 nodes/edges를 가져오기 위해 관계 새로고침
        await db.refresh(user_flow, ["nodes", "edges"])
        
        return {
            "flow_id": flow_id,
            "project_id": user_flow.project_id,
            "session_status": "completed",
            "current_turn": current_turn,
            "ai_message": result["message"],
            "interview_history": [h for h in history if h.get("role") != "_meta"],
            "user_flow": _serialize_flow(user_flow),
        }

    # ── 다음 제안 생성 (Layered Deep-Dive) ──
    prompt = PROPOSAL_FIRST_SYSTEM_PROMPT.format(tech_stack=tech_stack)
    messages = [SystemMessage(content=prompt)]
    
    # 전체 대화 컨텍스트 구성
    for h in history:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        elif h["role"] == "ai":
            try:
                # AI 메시지는 JSON 데이터에서 reply 부분만 추출하여 전달하거나 전체를 전달
                msg_data = json.loads(h["content"])
                messages.append(AIMessage(content=msg_data.get("ai_reply", h["content"])))
            except:
                messages.append(AIMessage(content=h["content"]))

    response = await llm.ainvoke(messages)
    
    try:
        import re
        content = response.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group()
        ai_data = json.loads(content)
    except:
        ai_data = {
            "ai_reply": response.content,
            "options": ["예, 계속 진행해주세요.", "다른 대안을 제안해주세요.", "직접 입력"],
            "ambiguity_score": meta.get("ambiguity_score", 50),
            "is_ready": False
        }

    history.append({"role": "ai", "content": json.dumps(ai_data, ensure_ascii=False), "turn": current_turn})
    meta["ambiguity_score"] = ai_data.get("ambiguity_score", 0)
    
    user_flow.interview_history = _set_meta(history, meta)
    user_flow.current_turn = current_turn
    await db.flush()

    return {
        "flow_id": flow_id,
        "project_id": user_flow.project_id,
        "session_status": "interviewing",
        "current_turn": current_turn,
        "ai_message": ai_data.get("ai_reply", ""),
        "options": ai_data.get("options", []),
        "ambiguity_score": ai_data.get("ambiguity_score", 0),
        "is_ready": ai_data.get("is_ready", False),
        "interview_history": [h for h in history if h.get("role") != "_meta"],
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

    # 온보딩/인터뷰에서 기획자(개발자)가 입력한 기술 스택 정보가 있으면 이를 우선 사용
    if not tech_stack or tech_stack == "최적 스택":
        meta = _get_meta(user_flow.interview_history or [])
        flow_tech_stack = meta.get("tech_stack")
        if flow_tech_stack and flow_tech_stack != "Unknown":
            tech_stack = flow_tech_stack

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
