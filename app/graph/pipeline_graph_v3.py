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
        temperature=0.1,
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
    tech_stack = state.get("technical_stack", "최적 스택")
    category = state.get("category", "전체")
    context = state.get("prd_context", "")
    parsed_text = state.get("parsed_text", "")

    system_prompt = (
        "🚀 FitHub AI V4: 직군별 파이프라인 생성 엔진\n"
        f"당신은 입력된 {category} 분야의 15년 경력 수석 아키텍트입니다. 당신의 목표는 제공된 {tech_stack}을 활용하여, "
        "PRD의 요구사항을 0.5~8시간 단위의 원자적(Atomic) GitHub 이슈로 분해하는 것입니다.\n\n"
        "## 🛠️ 1. 직군별 개발 시퀀스 (The Inside-Out Rule)\n"
        f"입력받은 category({category})에 따라 아래의 상향식 개발 순서를 엄격히 준수하십시오. 하위 레이어가 정의되지 않은 상태에서 상위 레이어를 먼저 계획하는 것은 금지됩니다.\n\n"
        "**CASE A: Backend (BE) 아키텍처 규칙**\n"
        "- L1: Persistence Foundation: DB 스키마 설계 및 JPA Entity 매핑.\n"
        "- L2: Data Access: JpaRepository 인터페이스 및 Query 로직 구현.\n"
        "- L3: Business Logic: @Service 레이어 알고리즘 및 트랜잭션 처리. (Controller 언급 금지)\n"
        "- L4: API Interface: @RestController, DTO 정의, 유효성 검증(@Valid).\n\n"
        "**CASE B: Frontend (FE) 아키텍처 규칙**\n"
        "- L1: UI Component: 디자인 시스템 기반 원자적 컴포넌트(Atoms/Molecules) 및 CSS 스타일링.\n"
        "- L2: Client State: Custom Hooks를 활용한 UI 상태 관리 로직 설계.\n"
        "- L3: API Client: Axios/Fetch 기반의 API 서비스 통신 계층 구현. (목업 데이터 포함)\n"
        "- L4: Data Binding: 실제 API 연동 및 컴포넌트 데이터 바인딩 통합.\n\n"
        "## 📐 2. 의존성 및 중복 방지 로직 (Guardrails)\n"
        f"- **직군 격리**: category가 '{category}'입니다. 이 직군에 해당하지 않는 작업(예: BE인데 UI 컴포넌트, FE인데 Repository/Controller)은 절대 생성하지 마십시오.\n"
        "- **의존성 체인**: 1번 스텝을 제외한 모든 스텝은 반드시 현재 직군 내의 직전 단계 번호를 depends_on에 포함해야 합니다.\n"
        "- **루핑 및 중복 금지**: 동일한 기술 스택 초기화나 중복된 기능을 여러 번 생성하지 마십시오. 전체 시퀀스가 끝나면 즉시 중단하십시오.\n"
        "- **할루시네이션 차단**: 제공된 <PRD_CONTENT>에 명시되지 않은 필드나 기능을 임의로 추가하지 마십시오.\n\n"
        "## 🧠 3. 이슈 생성 알고리즘 (MoT & INVEST)\n"
        "- **Atomic**: 숙련된 개발자가 8시간 이내에 PR(Pull Request)을 날릴 수 있는 규모인가?\n"
        "- **Testable**: 상세 내용 마지막에 \"성공 조건: [정량적 검증 기준]\"을 반드시 포함하십시오.\n"
        "  - BE 예시: \"성공 조건: JpaRepository의 특정 메서드에 대한 JUnit 테스트 통과\"\n"
        "  - FE 예시: \"성공 조건: Storybook에서 컴포넌트 렌더링 및 인터렉션 확인\"\n\n"
        "## 📝 4. 출력 형식 (Strict JSON)\n"
        "결과물은 반드시 아래 구조의 JSON 배열이어야 하며, 다른 설명 텍스트는 일절 배제하십시오.\n"
        "[\n"
        "  {\n"
        f"    \"step_task_description\": \"[{category}] 단계명 - 구체적 이슈 제목\",\n"
        f"    \"step_details\": [\"작업 내용 1\", \"작업 내용 2\", \"성공 조건: [정량적 검증 기준]\"],\n"
        f"    \"category\": \"{category}\",\n"
        "    \"priority\": 1,\n"
        f"    \"tech_stack\": [\"{tech_stack} 기반 세부 라이브러리\"],\n"
        "    \"depends_on\": [이전 sequence_number],\n"
        "    \"step_sequence_number\": 1\n"
        "  }\n"
        "]\n"
    )

    user_message = (
        f"<PRD_CONTENT>\n{parsed_text}\n</PRD_CONTENT>\n\n"
        f"<TECH_STACK>{tech_stack}</TECH_STACK>\n\n"
        f"<CONTEXT>{context}</CONTEXT>"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ]

    response = llm.invoke(messages)
    try:
        content = response.content.strip()
        if content.startswith("{"):
            parsed = json.loads(content)
            steps = parsed.get("steps", [parsed])
        else:
            start_idx = content.find("[")
            end_idx = content.rfind("]") + 1
            if start_idx != -1 and end_idx > 0:
                steps = json.loads(content[start_idx:end_idx])
            else:
                steps = json.loads(content)
        
        if not isinstance(steps, list): steps = [steps]
    except Exception as e:
        logger.error(f"[decomposer] JSON 파싱 실패: {e}")
        steps = []

    return {"completed_steps": steps, "todos": [], "iteration_count": 0}

def quality_validator(state: AgentState) -> dict:
    steps = state.get("completed_steps", [])
    if not steps: return {"completed_steps": []}

    valid_steps = []
    seen_titles = set()
    banned_keywords = ["Thymeleaf", "JSP", "Freemarker", "MVC", "Server Side Rendering", "SSR"]
    
    for step in steps:
        title = step.get("step_task_description", "") or step.get("title", "")
        details = step.get("step_details", []) or step.get("details", [])
        stack = step.get("tech_stack", [])
        category = step.get("category", "BE")
        seq = step.get("step_sequence_number", 0)
        deps = step.get("depends_on", [])

        # 1. 직군 간 교차 오염 검사 (Cross-contamination Check)
        content_str = str(title).lower() + " " + " ".join([str(d).lower() for d in details])
        if category == "FE":
            if any(k in content_str for k in ["controller", "repository", "jpa", "entity", "spring"]):
                logger.warning(f"[validator] FE 카테고리에 BE 작업 혼입 감지(Reject): {title}")
                continue
        elif category in ["BE", "DB"]:
            if any(k in content_str for k in ["react", "vue", "css", "component", "dom "]):
                logger.warning(f"[validator] BE 카테고리에 FE 작업 혼입 감지(Reject): {title}")
                continue

        # 2. SSR 금지 검사
        if any(any(bk.lower() in str(s).lower() for bk in banned_keywords) for s in [title] + stack):
            logger.warning(f"[validator] SSR 기술 감지(Reject): {title}")
            continue

        # 3. 루핑(중복) 검사
        if title in seen_titles:
            logger.warning(f"[validator] 중복 작업 감지(Reject): {title}")
            continue
        seen_titles.add(title)

        # 4. 성공 조건 포함 검사
        if not any("성공 조건" in str(d) for d in details):
            logger.warning(f"[validator] 성공 조건 누락: {title}")
            # 자동으로 직군에 맞는 기본 성공 조건 추가
            if category == "FE":
                details.append("성공 조건: UI 렌더링 및 콘솔 에러 없음 확인")
            else:
                details.append("성공 조건: 빌드 및 단위 테스트 통과")
            step["step_details"] = details

        # 5. BE 의존성 검사 (1번 제외)
        if category in ["BE", "DB"] and seq > 1 and not deps:
            logger.warning(f"[validator] BE 작업 의존성 누락: {title}")
            # 직전 번호로 자동 연결 시도
            step["depends_on"] = [seq - 1]

        # 6. priority 보정
        step["priority"] = max(1, min(2, step.get("priority", 1)))
        
        valid_steps.append(step)

    return {"completed_steps": valid_steps}

def finalize(state: AgentState) -> dict:
    steps = state.get("completed_steps", [])
    category = state.get("category", "BE")
    final_pipeline = []
    for idx, step in enumerate(steps):
        final_pipeline.append({
            "title": step.get("step_task_description", "") or step.get("title", f"Step {idx+1}"),
            "category": step.get("category", category),
            "priority": step.get("priority", 1),
            "tech_stack": step.get("tech_stack", []),
            "depends_on": step.get("depends_on", []),
            "details": step.get("step_details", []) or step.get("details", [])
        })
    return {"final_pipeline": final_pipeline}

def build_pipeline_graph_v3() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("parse_document", parse_document)
    graph.add_node("domain_decomposer", domain_decomposer)
    graph.add_node("quality_validator", quality_validator)
    graph.add_node("finalize", finalize)
    graph.set_entry_point("parse_document")
    graph.add_edge("parse_document", "domain_decomposer")
    graph.add_edge("domain_decomposer", "quality_validator")
    graph.add_edge("quality_validator", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()

pipeline_graph_v3 = build_pipeline_graph_v3()

