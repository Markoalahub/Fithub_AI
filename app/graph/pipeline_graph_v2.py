"""
LangGraph-based AI Pipeline Design Workflow (v2)

템플릿 기반 개선 버전:
- 기술스택 감지
- 템플릿 선택 (Spring, React 등)
- Phase 기반 파이프라인 생성 (Phase 1, 2, 3~N)
- 각 Phase별 상세 task 생성

Nodes:
  1. parse_pdf           — Docling으로 PRD PDF 파싱
  2. understand_prd      — GPT-4o로 PRD 목적/범위/핵심 요구사항 요약
  3. detect_tech_stack   — PDF에서 기술스택 추출 (Spring, React, FastAPI 등)
  4. select_template     — 기술스택에 맞는 템플릿 선택
  5. identify_domains    — 담당 도메인 식별
  6. generate_phases     — Phase 1, 2 + 도메인별 Phase 3~N 생성
  7. generate_items      — 각 Phase별 상세 체크리스트 생성
  8. prioritize          — 최종 정렬 및 검증
"""
import json
import tempfile
import os
from typing import TypedDict, Optional, List

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from docling.document_converter import DocumentConverter

from app.models.pipeline import PipelineItem
from app.config import get_settings
from app.templates.backend_templates import ALL_TEMPLATES


# ──────────────────────────────────────────────
# State
# ──────────────────────────────────────────────

class PipelineStateV2(TypedDict):
    requirements: str              # 기획자 요구사항 텍스트
    pdf_bytes: Optional[bytes]     # 업로드된 PDF 원본 바이트
    category: str                  # 직군 (FE, BE, AI 등)
    parsed_text: str               # Docling 파싱 결과
    prd_summary: str               # PRD 이해/요약 결과
    tech_stack: List[str]          # 감지된 기술스택 (Spring, React, FastAPI 등)
    template_name: str             # 선택된 템플릿 (Spring, React 등)
    selected_template: dict        # 실제 템플릿 내용
    domains: List[str]             # 직군이 담당할 도메인 영역
    phases: List[dict]             # 생성된 Phase 목록
    raw_items: str                 # LLM이 생성한 JSON 문자열
    pipeline: List[PipelineItem]   # 최종 파이프라인 아이템 목록


# ──────────────────────────────────────────────
# LLM 초기화
# ──────────────────────────────────────────────

def _get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.3,
        api_key=settings.openai_api_key,
    )


# ──────────────────────────────────────────────
# Node 1: PDF 파싱 (Docling)
# ──────────────────────────────────────────────

def parse_pdf(state: PipelineStateV2) -> PipelineStateV2:
    """Docling으로 PRD PDF를 파싱하여 구조화된 텍스트 추출"""
    pdf_bytes = state.get("pdf_bytes")

    if not pdf_bytes:
        return {**state, "parsed_text": ""}

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        parsed_text = result.document.export_to_markdown()
    finally:
        os.unlink(tmp_path)

    return {**state, "parsed_text": parsed_text}


# ──────────────────────────────────────────────
# Node 2: PRD 이해
# ──────────────────────────────────────────────

def understand_prd(state: PipelineStateV2) -> PipelineStateV2:
    """GPT-4o로 PRD 전체 목적·범위·핵심 요구사항 요약"""
    llm = _get_llm()

    prd_content = ""
    if state.get("parsed_text"):
        prd_content += f"## PRD 문서 내용\n{state['parsed_text']}\n\n"
    if state.get("requirements"):
        prd_content += f"## 기획자 추가 요구사항\n{state['requirements']}"

    messages = [
        SystemMessage(content=(
            "당신은 시니어 아키텍트입니다. "
            "PRD(Product Requirements Document)를 분석하여 "
            "프로젝트의 핵심 목표, 기술 범위, 주요 기능 요구사항을 요약하세요. "
            "요약은 이후 기술스택 선정과 파이프라인 설계에 사용됩니다."
        )),
        HumanMessage(content=(
            f"{prd_content}\n\n"
            "위 PRD를 분석하여 다음을 요약해주세요:\n"
            "1. 프로젝트의 핵심 목적 (1-2문장)\n"
            "2. 주요 기능 영역 및 범위\n"
            "3. 기술적 요구사항 및 제약사항\n"
            "4. 예상되는 아키텍처 (모놀리식, 마이크로서비스 등)\n"
            "5. 성능, 보안, 확장성 관련 요구사항"
        )),
    ]

    response = llm.invoke(messages)
    return {**state, "prd_summary": response.content}


# ──────────────────────────────────────────────
# Node 3: 기술스택 감지 (신규)
# ──────────────────────────────────────────────

def detect_tech_stack(state: PipelineStateV2) -> PipelineStateV2:
    """PDF와 요구사항에서 기술스택 감지"""
    llm = _get_llm()

    prd_content = state.get("prd_summary", "")
    requirements = state.get("requirements", "")

    messages = [
        SystemMessage(content=(
            "당신은 기술 스택 선정 전문가입니다. "
            "PRD 분석 결과와 요구사항을 바탕으로 프로젝트에서 사용할 기술스택을 식별하세요.\n\n"
            "가능한 기술스택:\n"
            "- 백엔드: Spring, FastAPI, Node.js, Django\n"
            "- 프론트엔드: React, Vue, Angular, Svelte\n"
            "- 기타: AI/ML (Python, TensorFlow), DevOps (Docker, K8s)\n\n"
            "반드시 JSON 배열 형식으로만 응답하세요."
        )),
        HumanMessage(content=(
            f"## PRD 분석\n{prd_content}\n\n"
            f"## 기획자 요구사항\n{requirements}\n\n"
            "위 내용을 바탕으로 사용될 기술스택을 식별해주세요.\n"
            "JSON 배열로만 응답하세요. 예시: [\"Spring\", \"React\", \"PostgreSQL\"]\n"
            "각 항목은 우리가 템플릿으로 지원하는 항목이어야 합니다."
        )),
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        tech_stack = json.loads(content)
        if not isinstance(tech_stack, list):
            tech_stack = [content]
    except json.JSONDecodeError:
        tech_stack = []

    return {**state, "tech_stack": tech_stack}


# ──────────────────────────────────────────────
# Node 4: 템플릿 선택 (신규)
# ──────────────────────────────────────────────

def select_template(state: PipelineStateV2) -> PipelineStateV2:
    """기술스택에 맞는 템플릿 선택"""
    tech_stack = state.get("tech_stack", [])

    # 감지된 기술스택 중에서 우리가 지원하는 템플릿 찾기
    selected_template = None
    template_name = None

    for tech in tech_stack:
        if tech in ALL_TEMPLATES:
            selected_template = ALL_TEMPLATES[tech]
            template_name = tech
            break

    # 만약 매칭되는 템플릿이 없으면 기본값 선택
    if not selected_template:
        # 기본적으로 Spring 백엔드 선택 (사용자 요청)
        selected_template = ALL_TEMPLATES.get("Spring")
        template_name = "Spring"

    return {
        **state,
        "template_name": template_name,
        "selected_template": selected_template,
    }


# ──────────────────────────────────────────────
# Node 5: 담당 도메인 식별
# ──────────────────────────────────────────────

def identify_domains(state: PipelineStateV2) -> PipelineStateV2:
    """선택된 템플릿 기반으로 담당할 도메인 영역 식별"""
    llm = _get_llm()
    template_name = state.get("template_name", "")
    prd_summary = state.get("prd_summary", "")
    requirements = state.get("requirements", "")

    # 템플릿별 도메인 예시 제공
    domain_examples = {
        "Spring": "User 관리, Authentication/JWT, Payment 처리, Notification, Analytics",
        "React": "로그인 페이지, 대시보드, 프로필 관리, 결제 페이지, 알림 센터",
        "FastAPI": "User API, ML Model Serving, Data Processing Pipeline",
    }

    example_text = domain_examples.get(template_name, "")

    messages = [
        SystemMessage(content=(
            f"당신은 시니어 아키텍트입니다. "
            f"{template_name} 기반 개발에서 담당할 도메인 영역을 식별하세요.\n"
            f"예시: {example_text}\n\n"
            "각 도메인은 독립적으로 개발 가능한 단위여야 합니다 (1-2시간 정도)."
        )),
        HumanMessage(content=(
            f"## PRD 분석\n{prd_summary}\n\n"
            f"## 기획자 요구사항\n{requirements}\n\n"
            f"위 내용을 바탕으로 {template_name}에서 개발해야 할 핵심 도메인을 식별해주세요.\n"
            "반드시 JSON 배열 형식으로만 응답하세요.\n"
            '예시: ["User 도메인", "Auth 도메인", "Payment 도메인"]\n'
            "규칙:\n"
            "- 각 도메인은 하나의 엔티티 중심\n"
            "- 1-2시간 내에 완성 가능한 크기\n"
            "- 5~8개 정도의 도메인으로 분리"
        )),
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        domains = json.loads(content)
        if not isinstance(domains, list):
            domains = [content]
    except json.JSONDecodeError:
        domains = [line.strip().lstrip("-•").strip()
                   for line in content.splitlines()
                   if line.strip()]

    return {**state, "domains": domains}


# ──────────────────────────────────────────────
# Node 6: Phase 생성 (신규)
# ──────────────────────────────────────────────

def generate_phases(state: PipelineStateV2) -> PipelineStateV2:
    """
    선택된 템플릿 기반으로 Phase 생성
    - Phase 1, 2: 고정 (초기 설정, 기반 구조)
    - Phase 3~N: 도메인별로 동적 생성
    """
    selected_template = state.get("selected_template", {})
    domains = state.get("domains", [])

    # 템플릿의 Phase 1, 2 복사
    base_phases = []
    for phase in selected_template.get("phases", []):
        if phase.get("type") in ["setup", "infrastructure"]:
            base_phases.append(phase)

    # Phase 3~N: 도메인별 동적 생성
    domain_phases = []
    for idx, domain in enumerate(domains, start=3):
        domain_phase = {
            "phase_num": idx,
            "name": f"{domain} 개발",
            "type": "domain",
            "domain_name": domain,
            "steps": []
        }
        domain_phases.append(domain_phase)

    phases = base_phases + domain_phases
    return {**state, "phases": phases}


# ──────────────────────────────────────────────
# Node 7: Phase별 상세 task 생성 (개선)
# ──────────────────────────────────────────────

def generate_items(state: PipelineStateV2) -> PipelineStateV2:
    """각 Phase별 상세 체크리스트 생성"""
    llm = _get_llm()

    phases = state.get("phases", [])
    template_name = state.get("template_name", "")
    prd_summary = state.get("prd_summary", "")
    requirements = state.get("requirements", "")

    all_items = []

    for phase in phases:
        phase_num = phase.get("phase_num")
        phase_name = phase.get("name")
        phase_type = phase.get("type")
        domain_name = phase.get("domain_name", "")

        # Phase 1, 2는 템플릿에서 직접 가져오기
        if phase_type in ["setup", "infrastructure"]:
            for step in phase.get("steps", []):
                priority = (phase_num - 1) * 10  # Phase 1 → 0~9, Phase 2 → 10~19

                item = PipelineItem(
                    title=step.get("title", ""),
                    priority=priority,
                    details=step.get("checklist", []),
                )
                all_items.append(item)

        # Phase 3~N (도메인별): LLM으로 생성
        elif phase_type == "domain":
            messages = [
                SystemMessage(content=(
                    f"당신은 10년 경력의 시니어 {template_name} 개발자입니다.\n"
                    f"{template_name} 개발 프로세스에 따라 '{domain_name}'을 개발할 때의 "
                    "구체적인 체크리스트를 작성하세요.\n\n"
                    "체크리스트는 1-2시간 내에 완성할 수 있는 크기여야 합니다.\n"
                    "각 항목은 매우 기술적이고 구체적이어야 합니다."
                )),
                HumanMessage(content=(
                    f"## PRD 분석\n{prd_summary}\n\n"
                    f"## 기획자 요구사항\n{requirements}\n\n"
                    f"## 개발 도메인\n{domain_name}\n\n"
                    f"위 '{domain_name}'을 {template_name}으로 개발할 때의 "
                    "상세한 구현 체크리스트를 JSON 형식으로 생성해주세요.\n\n"
                    "**템플릿 기반 단계:**\n"
                    "1. Entity/Model 설계\n"
                    "2. Repository/DAO 구현\n"
                    "3. Service/비즈니스 로직 구현\n"
                    "4. DTO 정의\n"
                    "5. Controller/API 엔드포인트\n"
                    "6. 검증 및 테스트\n\n"
                    "**반드시 아래 JSON 형식으로만 응답하세요:**\n"
                    """[
  {
    "title": "단계 제목 (동사로 시작)",
    "details": [
      "구체적인 구현 사항 1 (매우 기술적)",
      "구체적인 구현 사항 2",
      "구체적인 구현 사항 3",
      "구체적인 구현 사항 4",
      "완료 기준"
    ]
  }
]"""
                )),
            ]

            response = llm.invoke(messages)
            content = response.content.strip()

            if "```" in content:
                parts = content.split("```")
                for part in parts:
                    stripped = part.strip()
                    if stripped.startswith("json"):
                        content = stripped[4:].strip()
                        break
                    elif stripped.startswith("["):
                        content = stripped
                        break

            try:
                domain_items = json.loads(content)

                for idx, item_data in enumerate(domain_items):
                    priority = (phase_num - 1) * 10 + idx

                    item = PipelineItem(
                        title=item_data.get("title", ""),
                        priority=priority,
                        details=item_data.get("details", []),
                    )
                    all_items.append(item)
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 기본 항목 추가
                item = PipelineItem(
                    title=f"{domain_name} 개발",
                    priority=(phase_num - 1) * 10,
                    details=["상세 구현 정보 생성 실패", "수동으로 정의 필요"],
                )
                all_items.append(item)

    return {**state, "raw_items": json.dumps([{
        "title": item.title,
        "priority": item.priority,
        "details": item.details,
    } for item in all_items])}


# ──────────────────────────────────────────────
# Node 8: 우선순위 정렬 및 검증
# ──────────────────────────────────────────────

def prioritize(state: PipelineStateV2) -> PipelineStateV2:
    """파이프라인 아이템 파싱, 검증, 우선순위 정렬"""
    raw = state.get("raw_items", "")

    content = raw.strip()
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                content = stripped[4:].strip()
                break
            elif stripped.startswith("["):
                content = stripped
                break

    try:
        raw_list = json.loads(content)
    except json.JSONDecodeError:
        llm = _get_llm()
        fix_messages = [
            SystemMessage(content="JSON 형식 수정 전문가입니다. 주어진 텍스트에서 유효한 JSON 배열을 추출하세요."),
            HumanMessage(content=f"다음 텍스트에서 JSON 배열만 추출하여 응답하세요:\n\n{raw}"),
        ]
        fix_response = llm.invoke(fix_messages)
        raw_list = json.loads(fix_response.content.strip())

    items: List[PipelineItem] = []
    for item in raw_list:
        try:
            priority_val = int(item.get("priority", 999))
        except (ValueError, TypeError):
            priority_val = 999

        items.append(PipelineItem(
            title=item.get("title", ""),
            priority=priority_val,
            details=item.get("details", []),
        ))

    items.sort(key=lambda x: x.priority)
    return {**state, "pipeline": items}


# ──────────────────────────────────────────────
# 그래프 빌드
# ──────────────────────────────────────────────

def build_pipeline_graph_v2() -> StateGraph:
    graph = StateGraph(PipelineStateV2)

    graph.add_node("parse_pdf", parse_pdf)
    graph.add_node("understand_prd", understand_prd)
    graph.add_node("detect_tech_stack", detect_tech_stack)
    graph.add_node("select_template", select_template)
    graph.add_node("identify_domains", identify_domains)
    graph.add_node("generate_phases", generate_phases)
    graph.add_node("generate_items", generate_items)
    graph.add_node("prioritize", prioritize)

    graph.set_entry_point("parse_pdf")
    graph.add_edge("parse_pdf", "understand_prd")
    graph.add_edge("understand_prd", "detect_tech_stack")
    graph.add_edge("detect_tech_stack", "select_template")
    graph.add_edge("select_template", "identify_domains")
    graph.add_edge("identify_domains", "generate_phases")
    graph.add_edge("generate_phases", "generate_items")
    graph.add_edge("generate_items", "prioritize")
    graph.add_edge("prioritize", END)

    return graph.compile()


# 싱글톤 그래프 인스턴스
pipeline_graph_v2 = build_pipeline_graph_v2()
