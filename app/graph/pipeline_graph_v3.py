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
    
    logger.info(f"[parse_document] PDF 바이트 수신: {len(pdf_bytes) if pdf_bytes else 0} bytes")
    logger.info(f"[parse_document] requirements 길이: {len(requirements)} chars")
    
    if not pdf_bytes:
        logger.warning("[parse_document] PDF 없음 → requirements만 사용")
        return {"parsed_text": requirements, "pdf_bytes": None}

    parsed_text = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        logger.info(f"[parse_document] 임시 파일 생성: {tmp_path}")
        
        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        parsed_text = result.document.export_to_markdown()
        os.unlink(tmp_path)
        
        logger.info(f"[parse_document] PDF 파싱 성공! 추출된 텍스트 길이: {len(parsed_text)} chars")
        logger.info(f"[parse_document] 텍스트 미리보기: {parsed_text[:200]}...")
    except Exception as e:
        logger.error(f"[parse_document] PDF 파싱 실패: {e}", exc_info=True)
        parsed_text = ""

    # PDF 파싱 실패해도 requirements는 반드시 포함
    if parsed_text:
        full_context = f"사용자 요구사항:\n{requirements}\n\nPRD 상세 내용(PDF):\n{parsed_text}"
    else:
        logger.warning("[parse_document] PDF 텍스트 추출 실패 → requirements만 전달")
        full_context = requirements
    
    logger.info(f"[parse_document] 최종 전달 텍스트 길이: {len(full_context)} chars")
    return {"parsed_text": full_context, "pdf_bytes": None}


# ──────────────────────────────────────────────
# Node 2: domain_decomposer (Vertical Slice Orchestrator)
# ──────────────────────────────────────────────

def domain_decomposer(state: AgentState) -> dict:
    llm = _get_llm("gpt-4o")
    parsed_text = state.get("parsed_text", "")
    category = state.get("category", "BE")
    tech_stack = state.get("technical_stack", "최적 스택")
    
    system_prompt = (
        f"당신은 {tech_stack} 전문 소프트웨어 아키텍트입니다.\n"
        f"## 미션: 아래 '제공된 내용'만을 근거로 하여 {category} 개발 파이프라인을 기획하라.\n\n"
        "## 절대 규칙 (위반 시 시스템 오류):\n"
        f"1. **근거 없는 생성 금지**: 제공된 PRD/요구사항 문서에 명시되지 않은 기능(예: 문서에 없는데 상품, 주문, 추천 등 추가)을 임의로 생성하는 것을 엄격히 금지합니다. 오직 문서 내의 정보만 사용하세요.\n"
        f"2. **기술 스택 고정**: 반드시 사용자가 지정한 기술 스택 `{tech_stack}` 내에서만 설계하세요.\n"
        f"3. **직군 제한**: 반드시 '{category}' 직군이 수행해야 할 작업만 도출하세요.\n"
        "4. **의존성**: 동일 카테고리 내 선행 작업 id를 명시하세요.\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요 (구조만 따를 것):\n"
        '[\n'
        f'  {{"id": 1, "category": "{category}", "feature": "문서 내 기능명", "goal": "구체적 목표", "depends_on": []}}\n'
        ']'
    )
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"요구사항 및 PRD 내용: {parsed_text}")
    ]
    
    response = llm.invoke(messages)
    try:
        content = response.content.strip()
        # JSON 블록 추출 로직 강화 (정규표현식 대용으로 더 튼튼하게)
        start_idx = content.find("[")
        end_idx = content.rfind("]") + 1
        if start_idx != -1 and end_idx != 0:
            json_str = content[start_idx:end_idx]
            todos = json.loads(json_str)
        else:
            todos = json.loads(content)
            
        if not isinstance(todos, list):
            todos = [todos]
    except Exception as e:
        logger.error(f"V3 Decomposer JSON 파싱 실패: {e}")
        logger.error(f"원본 응답: {response.content}")
        # 실패 시 최소한의 작업이라도 수행하도록 폴백 유지하되 제목 수정
        todos = [{"id": 1, "category": category, "feature": "기획 분석", "goal": "요구사항에 따른 초기 개발 방향 설정", "depends_on": []}]
        
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
    category = state.get("category", "BE")
    tech_stack = state.get("technical_stack", "")
    feedback = state.get("feedback", "")
    
    system_prompt = (
        f"당신은 {tech_stack} 전문 {category} 개발자입니다.\n"
        f"## 미션: 전달받은 '{current_todo.get('feature')}' 기능을 상세 구현 스텝으로 변환하라.\n\n"
        "## 절대 규칙:\n"
        f"1. **기술 스택 제한**: 오직 `{tech_stack}` 관련 기술만 상세 작업(details)에 포함하세요.\n"
        f"2. **내용 일치**: 전달받은 기능의 목표({current_todo.get('goal')})를 벗어난 작업을 추가하지 마세요.\n"
        f"3. **카테고리**: [{category}]를 제목 앞에 붙이세요.\n"
        f"4. **태그**: tech_stack 배열에는 `{tech_stack}` 중 실제 사용된 기술 명칭을 넣으세요.\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요:\n"
        '{\n'
        f'  "title": "[{category}] 기능명 - 상세작업",\n'
        f'  "category": "{category}",\n'
        '  "priority": 1,\n'
        '  "tech_stack": ["사용기술1", "사용기술2"],\n'
        '  "details": ["문서에 근거한 구체적 작업 1", "문서에 근거한 구체적 작업 2"],\n'
        '  "depends_on": []\n'
        '}'
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

    # 4. 상세 작업 개수 검사 (너무 많으면 단위가 큰 것임)
    details = draft.get("details", [])
    if len(details) > 6:
        reasons.append(f"상세 작업이 {len(details)}개로 너무 많습니다. 단위를 더 쪼개세요.")
    if len(details) < 2:
        reasons.append("상세 작업이 너무 부족합니다. 구체적인 구현 단계를 포함하세요.")

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
    category = state.get("category", "BE")
    
    final_pipeline = []
    for idx, step in enumerate(steps):
        final_pipeline.append({
            "title": step.get("title", f"Step {idx+1}"),
            "category": step.get("category", category),
            "priority": step.get("priority", 1),
            "tech_stack": step.get("tech_stack", []),
            "depends_on": step.get("depends_on", []),
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
