"""
LangGraph-based AI Pipeline Design Workflow (v3.3) - Vertical Slice Edition

pipeImprove.md 전략 반영:
1. 수직적 슬라이스(Vertical Slice): 레이어 중심이 아닌 기능(Feature) 중심 분해
2. 명명 규칙 강제: [기능 명칭] - [수행할 기술적 목표]
3. E2E 흐름 강조: 하나의 작업이 Entity부터 Controller까지의 흐름을 포함하도록 설계
"""
import operator
import json
import logging
from typing import TypedDict, Annotated, List, Optional, Union
from langgraph.graph import StateGraph, END

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.config import get_settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# State Definition
# ──────────────────────────────────────────────

class AgentState(TypedDict):
    prd_context: str
    technical_stack: str
    todos: List[dict]
    completed_steps: Annotated[list, operator.add]
    feedback: str
    iteration_count: int
    
    pdf_bytes: Optional[bytes]
    parsed_text: str
    category: str
    current_step_draft: Optional[dict]
    final_pipeline: List[dict]


# ──────────────────────────────────────────────
# LLM 초기화
# ──────────────────────────────────────────────

def _get_llm(model_name="gpt-4o") -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=model_name,
        temperature=0.2,
        api_key=settings.openai_api_key,
    )


# ──────────────────────────────────────────────
# Node 1: 문서 처리 엔진
# ──────────────────────────────────────────────

def parse_document(state: AgentState) -> dict:
    import tempfile
    import os
    from docling.document_converter import DocumentConverter

    pdf_bytes = state.get("pdf_bytes")
    requirements = state.get("prd_context", "")
    
    if not pdf_bytes:
        return {"parsed_text": requirements, "pdf_bytes": None}

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        parsed_text = result.document.export_to_markdown()
        os.unlink(tmp_path)
    except Exception as e:
        logger.error(f"PDF 파싱 실패: {e}")
        parsed_text = ""

    full_context = f"사용자 요구사항:\n{requirements}\n\nPRD 상세 내용(PDF):\n{parsed_text}"
    return {"parsed_text": full_context, "pdf_bytes": None}


# ──────────────────────────────────────────────
# Node 2: domain_decomposer (Vertical Slice Orchestrator)
# ──────────────────────────────────────────────

def domain_decomposer(state: AgentState) -> dict:
    llm = _get_llm("gpt-4o")
    parsed_text = state.get("parsed_text", "")
    category = state.get("category", "풀스택")
    
    system_prompt = (
        f"당신은 {category} 도메인 아키텍트입니다.\n"
        "PRD를 분석하여 '버티컬 슬라이스(Vertical Slice)' 기반의 기능 목록을 추출하세요.\n"
        "기술 레이어(Entity, Service 등)로 쪼개지 말고, '사용자 가치를 제공하는 최소 기능 단위'로 계획을 세우세요.\n\n"
        "응답 형식 JSON 배열 예시:\n"
        '[\n  {"feature": "회원가입", "goal": "OAuth2.0 연동 및 유저 저장"},\n  {"feature": "포스트 작성", "goal": "이미지 업로드 및 게시글 저장"}\n]'
    )
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=parsed_text)
    ]
    
    response = llm.invoke(messages)
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        todos = json.loads(content)
    except:
        todos = [{"feature": "기본 기능", "goal": "요구사항 초기 구현"}]
        
    return {"todos": todos, "completed_steps": [], "iteration_count": 0}


# ──────────────────────────────────────────────
# Node 3: atomic_step_builder (Worker)
# ──────────────────────────────────────────────

def atomic_step_builder(state: AgentState) -> dict:
    llm = _get_llm("gpt-4o-mini")
    todos = state.get("todos", [])
    if not todos:
        return {}

    current_todo = todos[0]
    tech_stack = state.get("technical_stack", "최적 스택")
    feedback = state.get("feedback", "")
    
    system_prompt = (
        f"당신은 시니어 개발자입니다. 기술 스택: {tech_stack}\n"
        "주어진 기능을 '수직적 슬라이스' 원칙에 따라 하나의 실행 가능한 작업으로 변환하세요.\n"
        "1. 명명 규칙 준수: [기능 명칭] - [수행할 기술적 목표]\n"
        "2. E2E 흐름 포함: 가능하면 Entity부터 Controller까지 해당 기능의 흐름을 한꺼번에 처리\n"
        "3. 5-200-4 규칙 준수 (4시간 이내 분량)\n\n"
        "JSON 형식:\n"
        '{"title": "[기능명] - 액션명", "estimated_hours": 3, "details": ["하위 태스크 리스트"]}'
    )
    
    if feedback:
        system_prompt += f"\n\n이전 피드백 반영 사항: {feedback}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"처리할 기능: {json.dumps(current_todo, ensure_ascii=False)}")
    ]
    
    response = llm.invoke(messages)
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        step_draft = json.loads(content)
    except:
        step_draft = {"title": f"[{current_todo.get('feature')}] - {current_todo.get('goal')}", "estimated_hours": 4, "details": []}

    return {"current_step_draft": step_draft}


# ──────────────────────────────────────────────
# Node 4: quality_critic (Reviewer)
# ──────────────────────────────────────────────

def quality_critic(state: AgentState) -> dict:
    draft = state.get("current_step_draft")
    iteration = state.get("iteration_count", 0)
    
    if not draft:
        return {"feedback": "Draft missing"}

    title = draft.get("title", "")
    hours = draft.get("estimated_hours", 0)
    
    reasons = []
    
    # 1. 5-200-4 시간 검사
    if hours > 4:
        reasons.append(f"소요 시간({hours}h)이 4시간을 초과함")
        
    # 2. 명명 규칙 검사
    if not (title.startswith("[") and "] -" in title):
        reasons.append("명명 규칙 '[기능명] - 액션명'을 준수하지 않음")

    # 3. 수직적 슬라이스 여부 검사 (파편화 방지)
    fragment_keywords = ["Entity 정의", "Repository 작성", "Controller만", "DTO 생성"]
    for kw in fragment_keywords:
        if kw in title:
            reasons.append(f"단순 레이어 작업('{kw}')으로 파편화됨. 수직적 슬라이스로 통합 필요")
            break

    if iteration >= 3:
        return {
            "todos": state.get("todos", [])[1:],
            "completed_steps": [draft],
            "feedback": "",
            "iteration_count": 0,
            "current_step_draft": None
        }

    if not reasons:
        return {
            "todos": state.get("todos", [])[1:],
            "completed_steps": [draft],
            "feedback": "",
            "iteration_count": 0,
            "current_step_draft": None
        }
    else:
        return {
            "feedback": " | ".join(reasons),
            "iteration_count": iteration + 1
        }


# ──────────────────────────────────────────────
# Node 5: Finalize & Edge
# ──────────────────────────────────────────────

def route_after_critic(state: AgentState) -> str:
    if state.get("feedback"):
        return "atomic_step_builder"
    return "finalize" if not state.get("todos") else "atomic_step_builder"

def finalize(state: AgentState) -> dict:
    steps = state.get("completed_steps", [])
    tech_stack = state.get("technical_stack", "최적 스택")
    
    final_pipeline = []
    for idx, step in enumerate(steps):
        final_pipeline.append({
            "title": step.get("title", f"Step {idx+1}"),
            "priority": idx + 1,
            "duration": f"{step.get('estimated_hours', 2)} hours",
            "tech_stack": tech_stack,
            "details": step.get("details", [])
        })
        
    return {"final_pipeline": final_pipeline}


def build_pipeline_graph_v3() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("parse_document", parse_document)
    graph.add_node("domain_decomposer", domain_decomposer)
    graph.add_node("atomic_step_builder", atomic_step_builder)
    graph.add_node("quality_critic", quality_critic)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("parse_document")
    graph.add_edge("parse_document", "domain_decomposer")
    graph.add_edge("domain_decomposer", "atomic_step_builder")
    graph.add_edge("atomic_step_builder", "quality_critic")
    graph.add_conditional_edges("quality_critic", route_after_critic, {"atomic_step_builder": "atomic_step_builder", "finalize": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()

pipeline_graph_v3 = build_pipeline_graph_v3()
