import operator
import json
import logging
from typing import TypedDict, Annotated, List, Optional, Union
from langgraph.graph import StateGraph, END

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.config import get_settings

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    prd_context: str            # 프론트엔드 전달 원본 (인터뷰 포함)
    technical_stack: str
    todos: List[dict]
    completed_steps: List[dict]
    feedback: str
    iteration_count: int
    pdf_bytes: Optional[bytes]
    interview_summary: str      # 정제된 인터뷰 요약
    pdf_content: str            # PDF 추출 원본
    refined_requirements: str    # 최종 통합 설계 가이드
    category: str
    current_step_draft: Optional[dict]
    final_pipeline: List[dict]

def _get_llm(model_name="gpt-4o") -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=model_name,
        temperature=0.1,
        api_key=settings.openai_api_key,
    )

def parse_document(state: AgentState) -> dict:
    import tempfile
    import os
    from docling.document_converter import DocumentConverter

    pdf_bytes = state.get("pdf_bytes")
    requirements = state.get("prd_context", "")
    
    # 1. 인터뷰/텍스트 요구사항 분리 및 추출
    # 프론트엔드에서 🚀 [Ouroboros 사전 인터뷰 최종 요약] 태그를 사용함
    interview_part = ""
    if "🚀 [Ouroboros 사전 인터뷰 최종 요약]" in requirements:
        parts = requirements.split("🚀 [Ouroboros 사전 인터뷰 최종 요약]")
        interview_part = parts[1].split("📝 [기존 요구사항]")[0].strip()
    
    # 2. PDF 파싱
    pdf_content = ""
    if pdf_bytes:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            pdf_content = result.document.export_to_markdown()
            os.unlink(tmp_path)
            logger.info(f"[parse_document] PDF 파싱 성공: {len(pdf_content)} 자")
        except Exception as e:
            logger.error(f"[parse_document] PDF 파싱 실패: {e}")

    return {
        "interview_summary": interview_part, 
        "pdf_content": pdf_content,
        "pdf_bytes": None # 메모리 절약을 위해 바이너리 제거
    }

def requirement_refiner(state: AgentState) -> dict:
    """방대한 인터뷰와 PDF 내용을 통합하여 압축된 설계 가이드를 생성함"""
    llm = _get_llm("gpt-4o-mini") # 요약은 빠른 모델 사용
    interview = state.get("interview_summary", "")
    pdf = state.get("pdf_content", "")
    original_req = state.get("prd_context", "")

    system_prompt = (
        "당신은 요구사항 분석 전문가입니다. 제공된 인터뷰 내역과 PDF 문서를 통합하여 "
        "개발자가 파이프라인을 설계할 때 참고할 '핵심 설계 가이드'를 작성하세요.\n"
        "1. 인터뷰 내용은 기획자와의 최종 합의사항이므로 PDF 내용보다 우선합니다.\n"
        "2. 중복된 내용은 제거하고, 기술적 제약사항과 핵심 비즈니스 로직 위주로 요약하세요.\n"
        "3. 내용이 너무 길면 핵심만 리스트 형태로 압축하세요."
    )
    
    user_message = (
        f"### [최종 인터뷰 합의사항]\n{interview if interview else '내역 없음'}\n\n"
        f"### [원본 PDF 로직]\n{pdf if pdf else '내역 없음'}\n\n"
        f"### [기타 요구사항]\n{original_req}"
    )
    
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    response = llm.invoke(messages)
    
    return {"refined_requirements": response.content}

def domain_decomposer(state: AgentState) -> dict:
    llm = _get_llm("gpt-4o")
    tech_stack = state.get("technical_stack", "Spring Boot, JPA")
    category = state.get("category", "BE")
    refined_requirements = state.get("refined_requirements", "")

    scope_constraint = ""
    if category == "BE":
        scope_constraint = (
            "당신은 오직 **백엔드 서버와 데이터베이스** 아키텍처만 설계해야 합니다.\n"
            "- DB 스키마 설계 및 API 로직 구현에 집중하십시오.\n"
            "- UI/UX 구현은 절대 포함하지 마십시오."
        )
    elif category == "FE":
        scope_constraint = (
            "당신은 오직 **프론트엔드 및 클라이언트 애플리케이션**만 설계해야 합니다.\n"
            "- UI 컴포넌트 개발 및 API 연동에 집중하십시오.\n"
            "- DB 설계나 서버 측 트랜잭션 구현은 절대 포함하지 마십시오."
        )

    system_prompt = (
        f"🚀 FitHub AI: {category} 전문 파이프라인 설계 엔진\n"
        f"## ⚠️ 직군 격리 지침\n{scope_constraint}\n\n"
        "## 💡 설계 원칙: Atomic Task 분해 (매우 중요)\n"
        "1. 제공된 기획(PRD) 및 요구사항을 기반으로 시스템을 구축하기 위한 모든 작업 단위를 도출하십시오.\n"
        "2. **[정보 통합 지침]**: 제공된 정보는 두 가지 섹션으로 구성됩니다.\n"
        "   - `### [중요] 1. 사용자 최종 합의 및 인터뷰 요약`: 기획자와의 최신 합의 사항입니다. PRD의 모호한 부분을 이 내용이 결정합니다.\n"
        "   - `### [상세 가이드] 2. PRD 문서 분석 결과`: 시스템의 전체적인 로직과 비즈니스 규칙이 담긴 근간입니다.\n"
        "   **반드시** PRD의 상세 로직을 기반으로 하되, 인터뷰에서 변경되거나 구체화된 사양을 적용하여 설계하십시오. 어느 한쪽만 반영해서는 안 됩니다.\n"
        "3. 파이프라인이 너무 뭉뚱그려져 있으면(예: '인증 시스템 개발' 단 하나) 절대 안 됩니다. \n"
        "4. 반드시 원자적(Atomic) 수준으로 쪼개십시오 (예: 'DB 스키마 설계', 'OAuth 엔드포인트 구현', 'JWT 검증 필터 개발' 등).\n"
        "5. 최소 7개 이상의 매우 구체적이고 실무적인 스텝으로 분리하여 순차적으로 나열하십시오.\n"
        "6. **[매우 중요]** 각 스텝의 `details` 배열에 들어가는 항목들은 각각 **독립적인 하나의 GitHub 이슈(Issue)** 로 발행될 예정입니다.\n"
        "   따라서 단순한 설명이나 서술어가 아니라, 개발자가 즉시 티켓으로 할당받아 작업할 수 있는 '명확하고 구체적인 태스크(Task)' 형태로 작성하십시오.\n"
        "   (예: '사용자 로그인 기능 구현' (X) -> 'JWT 기반 OAuth2 로그인 인증 API 엔드포인트 구현 및 토큰 발급 로직 작성' (O))\n"
        "## 💡 출력 가이드 (Strict JSON 배열만 출력)\n"
        "[\n"
        "  {\n"
        "    \"title\": \"[세부 모듈] 원자적 작업 그룹명\",\n"
        "    \"details\": [\"[API] 로그인 인증 API 엔드포인트 구현\", \"[DB] 사용자 세션 및 토큰 관리 테이블 스키마 설계\", \"[Test] OAuth2 콜백 통합 테스트 코드 작성\"],\n"
        "    \"tech_stack\": [\"사용 기술\"]\n"
        "  }\n"
        "]"
    )

    user_message = f"기술 스택: {tech_stack}\n\n<REFINED_GUIDE>\n{refined_requirements}\n</REFINED_GUIDE>"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    response = llm.invoke(messages)
    
    try:
        content = response.content.strip()
        start_idx = content.find("[")
        end_idx = content.rfind("]") + 1
        steps = json.loads(content[start_idx:end_idx])
    except Exception as e:
        logger.error(f"[decomposer] JSON 파싱 에러: {e}")
        steps = []

    normalized_steps = []
    for step in steps:
        # 데이터 타입 안정성 확보 (Robust Mapping)
        raw_details = step.get("details") or step.get("description") or ["상세 내용 정의 필요"]
        if isinstance(raw_details, str):
            raw_details = [raw_details] # 문자열이면 리스트로 감싸기
            
        raw_tech = step.get("tech_stack") or step.get("tech") or []
        if isinstance(raw_tech, str):
            raw_tech = [raw_tech]

        normalized = {
            "title": step.get("title") or step.get("task") or "분석된 작업",
            "details": raw_details,
            "category": step.get("category") or category,
            "priority": step.get("priority") or 1,
            "tech_stack": raw_tech,
            "depends_on": step.get("depends_on") or []
        }
        normalized_steps.append(normalized)

    return {"completed_steps": normalized_steps}

def quality_validator(state: AgentState) -> dict:
    steps = state.get("completed_steps", [])
    valid_steps = []
    seen_titles = set()
    for step in steps:
        title = (step.get("title") or "").lower()
        if not title or title in seen_titles: continue
        seen_titles.add(title)
        valid_steps.append(step)
    return {"completed_steps": valid_steps}

def finalize(state: AgentState) -> dict:
    return {"final_pipeline": state.get("completed_steps", [])}

def build_pipeline_graph_v3() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("parse_document", parse_document)
    graph.add_node("requirement_refiner", requirement_refiner)
    graph.add_node("domain_decomposer", domain_decomposer)
    graph.add_node("quality_validator", quality_validator)
    graph.add_node("finalize", finalize)
    
    graph.set_entry_point("parse_document")
    graph.add_edge("parse_document", "requirement_refiner")
    graph.add_edge("requirement_refiner", "domain_decomposer")
    graph.add_edge("domain_decomposer", "quality_validator")
    graph.add_edge("quality_validator", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()

pipeline_graph_v3 = build_pipeline_graph_v3()
